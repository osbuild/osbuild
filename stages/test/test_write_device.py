#!/usr/bin/python3

import struct
from unittest.mock import call, mock_open, patch

import pytest  # type: ignore

STAGE_NAME = "org.osbuild.write-device"


def create_args(tree):
    tree.mkdir()
    a_file = tree / "a-file"
    a_file.write_text("Some content")

    options = {
        "from": "input://tree/a-file"
    }
    devices = {
        "device": {
            "path": "/dev/loop2",
        },
    }
    args = {
        "inputs": {
            "tree": {
                "path": f"{tree}",
            }
        },
        "devices": devices,
        "options": options,
    }
    return args


def block_device_size(size):
    return struct.pack('L', size)


@patch("subprocess.run")
@patch("builtins.open", mock_open(read_data="data"))
def test_write_device(mocked_run, tmp_path, stage_module):
    tree = tmp_path / "tree"
    args = create_args(tree)

    with patch("fcntl.ioctl", return_value=block_device_size(1024)):
        stage_module.main(args, args["devices"], args["options"])

    assert mocked_run.call_args_list == [
        call(["dd", f"if={tree}/a-file", "of=/dev/loop2", "status=progress", "conv=fsync"], check=True)]


@patch("builtins.open", mock_open(read_data="data"))
def test_write_device_size_check(tmp_path, stage_module):
    tree = tmp_path / "tree"
    args = create_args(tree)

    with pytest.raises(ValueError, match=r"File to large for device"):
        with patch("fcntl.ioctl", return_value=block_device_size(4)):
            stage_module.main(args, args["devices"], args["options"])
