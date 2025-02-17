#!/usr/bin/python3

import unittest.mock

import pytest

STAGE_NAME = "org.osbuild.qemu"


@pytest.mark.parametrize("format_opts,expected", [
    ({}, []),
    ({"adapter_type": "ide"}, ["-o", "adapter_type=ide"]),
    ({"compat6": True}, ["-o", "compat6"]),
    ({"compat6": True, "subformat": "streamOptimized"}, ["-o", "compat6,subformat=streamOptimized"]),
])
@unittest.mock.patch("subprocess.run")
def test_qemu_cmdline(mock_run, tmp_path, stage_module, format_opts, expected):
    inputs = {
        "image": {
            "path": "path/to/image.raw",
            "data": {
                "files": {
                    f"sha256:{'1' * 64}": {},
                }
            }
        }
    }
    filename = "file.vmdk"
    options = {
        "filename": filename,
        "format": {
            "type": "vmdk"
        }
    }
    options["format"].update(format_opts)
    stage_module.main(inputs, tmp_path, options)

    expected = [
        "qemu-img",
        "convert",
        "-O", "vmdk",
        "-c",
        *expected,
        "path/to/image.raw/sha256:1111111111111111111111111111111111111111111111111111111111111111",
        f"{tmp_path}/file.vmdk",
    ]
    mock_run.assert_called_with(expected, check=True)
