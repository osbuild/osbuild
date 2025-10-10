#!/usr/bin/python3

import os
import os.path
import subprocess
from unittest.mock import call, patch

import pytest

import osbuild.testutil
from osbuild.testutil import has_executable, make_container, make_fake_images_inputs

STAGE_NAME = "org.osbuild.container-deploy"


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
def test_container_deploy_integration(tmp_path, stage_module):
    # build two containers and overlay files to test for
    # https://github.com/containers/storage/issues/1779
    with make_container(tmp_path, {"file1": "file1 from base"}) as base_tag:
        with make_container(tmp_path, {"file1": "file1 from final layer"}, base_tag) as cont_tag:
            # export for the container-deploy stage
            fake_oci_path = tmp_path / "fake-container"
            subprocess.check_call([
                "podman", "save",
                "--format=oci-archive",
                f"--output={fake_oci_path}",
                cont_tag,
            ])

    inputs = make_fake_images_inputs(fake_oci_path, "some-name")
    output_dir = tmp_path / "output"
    options = {}

    with patch("os.makedirs", wraps=os.makedirs) as mocked_makedirs:
        stage_module.main(inputs, output_dir, options)

    assert output_dir.exists()
    assert (output_dir / "file1").read_bytes() == b"file1 from final layer"

    assert mocked_makedirs.call_args_list == [call("/var/tmp", mode=0o1777, exist_ok=True)]


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
def test_container_deploy_exclude(tmp_path, stage_module):
    with make_container(tmp_path, {
        "file1": "file1 content",
        "file2": "file2 content",
        "dir1/file3": "dir1/file3 content",
        "dir2/file4": "dir2/file4 content",
    }) as base_tag:
        # export for the container-deploy stage
        fake_oci_path = tmp_path / "fake-container"
        subprocess.check_call([
            "podman", "save",
            "--format=oci-archive",
            f"--output={fake_oci_path}",
            base_tag,
        ])

    inputs = make_fake_images_inputs(fake_oci_path, "some-name")
    options = {
        "exclude": [
            "file2",
            "dir2/",
        ],
    }
    output_dir = tmp_path / "output"

    stage_module.main(inputs, output_dir, options)
    assert output_dir.exists()
    assert (output_dir / "file1").read_bytes() == b"file1 content"
    assert not (output_dir / "file2").exists()
    assert (output_dir / "dir1/file3").read_bytes() == b"dir1/file3 content"
    assert not (output_dir / "dir2/file4").exists()
    assert not (output_dir / "dir2").exists()


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
@pytest.mark.parametrize("remove_signatures", [True, False])
def test_remove_signatures(tmp_path, stage_module, remove_signatures):
    with make_container(tmp_path, {}) as cont_tag:
        # export for the container-deploy stage
        fake_oci_path = tmp_path / "fake-container"
        subprocess.check_call([
            "podman", "save",
            "--format=oci-archive",
            f"--output={fake_oci_path}",
            cont_tag,
        ])
    inputs = make_fake_images_inputs(fake_oci_path, "some-name")

    fake_skopeo = textwrap.dedent("""\
    #! /bin/sh
    /usr/bin/skopeo $@
    """)

    with osbuild.testutil.mock_command("skopeo", fake_skopeo) as args:
        inputs = make_fake_images_inputs(fake_oci_path, "some-name")
        options = {
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
