#!/usr/bin/python3

import os
import os.path
import random
import string
import subprocess
from unittest.mock import call, patch

import pytest

from osbuild.testutil import has_executable, make_fake_tree
from osbuild.testutil.imports import import_module_from_path


def make_container(tmp_path, tag, fake_content, base="scratch"):
    fake_container_src = tmp_path / "fake-container-src"
    make_fake_tree(fake_container_src, fake_content)
    fake_containerfile_path = fake_container_src / "Containerfile"
    container_file_content = f"""
    FROM {base}
    COPY . .
    """
    fake_containerfile_path.write_text(container_file_content, encoding="utf8")
    subprocess.check_call([
        "podman", "build",
        "--no-cache",
        "-f", os.fspath(fake_containerfile_path),
        "-t", tag,
    ])


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
def test_container_deploy_integration(tmp_path):
    stage_path = os.path.join(os.path.dirname(__file__), "../org.osbuild.container-deploy")
    stage = import_module_from_path("stage", stage_path)

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

    with patch("os.makedirs", wraps=os.makedirs) as mocked_makedirs:
        stage.main(inputs, output_dir)

    assert output_dir.exists()
    assert (output_dir / "file1").read_bytes() == b"file1 from final layer"

    assert mocked_makedirs.call_args_list == [call("/var/tmp", mode=0o1777, exist_ok=True)]
