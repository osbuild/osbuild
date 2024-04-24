#!/usr/bin/python3
import json
import os
import subprocess

import pytest

from osbuild import testutil
from osbuild.testutil import has_executable, make_container

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


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
@pytest.mark.parametrize("dest_type,local_output_path", [
    ("dir", "/tmp/test-output-skopeo-dir"),
    ("oci-archive", "/tmp/test-output-skopeo.tar"),
    ("oci", "/tmp/test-output-skopeo-dir"),
])
def test_skopeo_copy(tmp_path, stage_module, dest_type, local_output_path):
    with make_container(tmp_path, {"file1": "file1 from final layer"}) as cont_tag:
        # export for the container-deploy stage
        fake_container_dst = tmp_path / "fake-container"
        subprocess.check_call([
            "podman", "save",
            "--format=oci-archive",
            f"--output={fake_container_dst}",
            cont_tag,
        ])

    inputs = {
        "images": {
            # seems to be unused with fake_container_path?
            "path": fake_container_dst,
            "data": {
                "archives": {
                    fake_container_dst: {
                        "format": "oci-archive",
                        "name": cont_tag,
                    },
                },
            },
        },
    }

    output_dir = tmp_path / "output"
    options = {
        "destination": {
            "type": dest_type,
            "path": local_output_path
        }
    }

    stage_module.main(inputs, output_dir, options)

    assert output_dir.exists()

    result = output_dir / local_output_path.lstrip("/")
    assert result.exists()

    if dest_type == "dir":
        assert (result / "version").exists()

        manifest_file = (result / "manifest.json")
    elif dest_type == "oci-archive":
        # TBD extract TAR and check content
        assert result.exists()
    elif dest_type == "oci":
        assert (result / "oci-layout").exists()

        index_file = (result / "index.json")
        assert index_file.exists()

        data = json.loads(index_file.read_bytes())

        assert data.get("manifests") is not None, "'index.json' seems corrupt - no 'manifests' section found"
        assert data["manifests"][0].get("digest") is not None, \
            "'manifest.json' seems corrupt - no 'manifests[0].digest' section found"
        data_digest = data["manifests"][0]["digest"].split(':')

        manifest_file = result / "blobs" / data_digest[0] / data_digest[1]

    if dest_type in ["dir", "oci"]:
        assert manifest_file.exists()

        data = json.loads(manifest_file.read_bytes())

        assert data.get("config") is not None, "'manifest.json' seems corrupt - no 'config' section found"

        assert data["config"].get("digest") is not None, \
            "'manifest.json' seems corrupt - no 'config.digest' section found"
