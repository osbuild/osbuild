#!/usr/bin/python3

import os
import os.path
import random
import string
import subprocess
import textwrap
from unittest.mock import call, patch

import pytest

import osbuild.testutil
from osbuild.testutil import has_executable, make_container, make_fake_tree

STAGE_NAME = "org.osbuild.container-deploy"


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
def test_container_deploy_integration(tmp_path, stage_module):
    # build two containers and overlay files to test for
    # https://github.com/containers/storage/issues/1779
    base_tag = "cont-base-" + "".join(random.choices(string.digits, k=12))
    make_container(tmp_path, base_tag, {"file1": "file1 from base"})
    cont_tag = "cont" + "".join(random.choices(string.digits, k=12))
    make_container(tmp_path, cont_tag, {"file1": "file1 from final layer"}, base_tag)
    # export for the container-deploy stage
    fake_container_dst = tmp_path / "fake-container"
    subprocess.check_call([
        "podman", "save",
        "--format=oci-archive",
        f"--output={fake_container_dst}",
        cont_tag,
    ])
    # and remove from podman
    subprocess.check_call(["podman", "rmi", cont_tag, base_tag])

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
    options = {}

    with patch("os.makedirs", wraps=os.makedirs) as mocked_makedirs:
        stage_module.main(inputs, output_dir, options)

    assert output_dir.exists()
    assert (output_dir / "file1").read_bytes() == b"file1 from final layer"

    assert mocked_makedirs.call_args_list == [call("/var/tmp", mode=0o1777, exist_ok=True)]


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
def test_container_deploy_exclude(tmp_path, stage_module):
    base_tag = "cont-base-" + "".join(random.choices(string.digits, k=12))
    make_container(tmp_path, base_tag, {
        "file1": "file1 content",
        "file2": "file2 content",
        "dir1/file3": "dir1/file3 content",
        "dir2/file4": "dir2/file4 content",
    })
    # export for the container-deploy stage
    fake_container_dst = tmp_path / "fake-container"
    subprocess.check_call([
        "podman", "save",
        "--format=oci-archive",
        f"--output={fake_container_dst}",
        base_tag,
    ])
    # and remove from podman
    subprocess.check_call(["podman", "rmi", base_tag])

    inputs = {
        "images": {
            # seems to be unused with fake_container_path?
            "path": fake_container_dst,
            "data": {
                "archives": {
                    fake_container_dst: {
                        "format": "oci-archive",
                        "name": base_tag,
                    },
                },
            },
        },
    }
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


def test_container_deploy_error(stage_module):
    fake_podman = textwrap.dedent("""\
    #!/bin/sh
    echo "some msg on stdout"
    echo "other error on stderr" >&2
    exit 1
    """)
    with osbuild.testutil.mock_command("podman", fake_podman):
        with pytest.raises(RuntimeError) as exp:
            with stage_module.mount_container("some-image-tag"):
                pass
    assert "some msg on stdout" not in str(exp.value)
    assert "other error on stderr" in str(exp.value)
