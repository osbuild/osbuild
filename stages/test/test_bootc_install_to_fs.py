#!/usr/bin/python3

import os.path
from contextlib import contextmanager
from unittest.mock import call, patch

from osbuild.testutil.imports import import_module_from_path


@patch("subprocess.run")
def test_bootc_install_to_fs(mock_run, tmp_path):
    stage_path = os.path.join(os.path.dirname(__file__), "../org.osbuild.bootc.install-to-filesystem")
    stage = import_module_from_path("bootc_install_to_fs_stage", stage_path)

    inputs = {
        "images": {
            "path": "/input/images/path",
            "data": {
                "archives": {
                    "/input/images/path": {
                        "format": "oci-archive",
                        "name": "some-img-name",
                    },
                },
            },
        },
    }
    mounts = {
        "root": {
            "path": "/path/to/root",
        },
    }

    @contextmanager
    def faked_tmp_dir():
        yield tmp_path
    with patch("tempfile.TemporaryDirectory", side_effect=faked_tmp_dir):
        stage.main(inputs, mounts)

    assert len(mock_run.call_args_list) == 1
    assert mock_run.call_args_list == [
        call(["bootc", "install", "to-filesystem",
              "--source-imgref", f"oci-archive:{tmp_path}/image",
              "--skip-fetch-check", "--generic-image",
              "/path/to/root"], check=True)
    ]
