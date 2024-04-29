#!/usr/bin/python3
import json
import os
import subprocess
import tarfile

import pytest

from osbuild import testutil
from osbuild.testutil import has_executable, make_container, make_fake_images_inputs

STAGE_NAME = "org.osbuild.skopeo"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({}, "'destination' is a required property"),
    ({"destination": {}}, "is not valid under any of the given schemas"),
    ({"destination": {"type": "foo"}}, "is not valid under any of the given schemas"),
    ({"destination": {"type": "oci"}}, "is not valid under any of the given schemas"),
    ({"destination": {"type": "dir"}}, "is not valid under any of the given schemas"),
    ({"destination": {"type": "os-archive"}}, "is not valid under any of the given schemas"),
    ({"destination": {"type": "dir", "path": "/foo"}, "remove-signatures": "YesPlease"},
     "'YesPlease' is not of type 'boolean'"),
    # good
    ({"destination": {"type": "oci", "path": "/foo"}}, ""),
    ({"destination": {"type": "oci-archive", "path": "/foo"}}, ""),
    ({"destination": {"type": "dir", "path": "/foo"}}, ""),
    ({"destination": {"type": "dir", "path": "/foo"}, "remove-signatures": True}, ""),

    # this one might not be expected but it's valid because we don't require any
    # *inputs* and it'll be a no-op in the stage
    ({"destination": {"type": "containers-storage"}}, ""),
])
def test_schema_validation_skopeo(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": {},
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


def make_fake_oci_archive(tmp_path):
    with make_container(tmp_path, {"file1": "file1 from final layer"}) as cont_tag:
        # export for the container-deploy stage
        fake_container_dst = tmp_path / "fake-container"
        subprocess.check_call([
            "podman", "save",
            "--format=oci-archive",
            f"--output={fake_container_dst}",
            cont_tag,
        ])
    return fake_container_dst


def assert_manifest_file(manifest_file):
    assert manifest_file.exists()
    data = json.loads(manifest_file.read_bytes())
    assert data.get("config") is not None, \
        "'manifest.json' seems corrupt - no 'config' section found"
    assert data["config"].get("digest") is not None, \
        "'manifest.json' seems corrupt - no 'config.digest' section found"


def _test_skopeo_copy(tmp_path, stage_module, typ, dest_name):
    fake_oci_path = make_fake_oci_archive(tmp_path)
    inputs = make_fake_images_inputs(fake_oci_path, "some-name")

    output_dir = tmp_path / "output"
    local_path = f"/some/{dest_name}"
    options = {
        "destination": {
            "type": typ,
            "path": local_path,
        }
    }
    stage_module.main(inputs, output_dir, options)
    result = output_dir / local_path.lstrip("/")
    assert result.exists()
    return result


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
def test_skopeo_copy_dir(tmp_path, stage_module):
    result_path = _test_skopeo_copy(tmp_path, stage_module, "dir", "skopeo-dir")
    assert (result_path / "version").exists()
    assert_manifest_file(result_path / "manifest.json")


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
def test_skopeo_copy_oci_archive(tmp_path, stage_module):
    result_path = _test_skopeo_copy(tmp_path, stage_module, "oci-archive", "skopeo-archive.tar")
    assert result_path.exists()
    with tarfile.open(result_path) as tf:
        assert tf


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
def test_skopeo_copy_oci(tmp_path, stage_module):
    result_path = _test_skopeo_copy(tmp_path, stage_module, "oci", "skopeo-archive-oci")
    index_file = (result_path / "index.json")
    assert index_file.exists()

    data = json.loads(index_file.read_bytes())
    assert data.get("manifests") is not None, "'index.json' seems corrupt - no 'manifests' section found"
    assert data["manifests"][0].get("digest") is not None, \
        "'manifest.json' seems corrupt - no 'manifests[0].digest' section found"
    data_digest = data["manifests"][0]["digest"].split(':')
    manifest_file = result_path / "blobs" / data_digest[0] / data_digest[1]
    assert_manifest_file(manifest_file)


@pytest.mark.parametrize("remove_signatures", [True, False])
def test_skopeo_copy_remove_signatures(tmp_path, stage_module, remove_signatures):
    # We are completely faking everything here, because we mock out skopeo
    fake_oci_path = tmp_path / "fake-container"
    inputs = make_fake_images_inputs(fake_oci_path, "some-name")

    with testutil.mock_command("skopeo", "") as args:
        options = {
            "destination": {
                "type": "oci",
                "path": "/tmp/test-output-skopeo-dir",
            },
            "remove-signatures": remove_signatures,
        }
        output_dir = tmp_path / "output"
        stage_module.main(inputs, output_dir, options)

        if remove_signatures:
            # Check that skopeo has --remove-signatures right after the copy subcommand
            assert args.call_args_list[0][0:2] == ["copy", "--remove-signatures"]
        else:
            # Check that --remove-signatures is not present in the skopeo command
            assert "--remove-signatures" not in args.call_args_list[0]
