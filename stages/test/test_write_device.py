#!/usr/bin/python3

import contextlib
import os
import struct
import subprocess
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

    with pytest.raises(ValueError, match=r"File too large \(0.0 mb\) for device \(0.0 mb\)"):
        with patch("fcntl.ioctl", return_value=block_device_size(4)):
            stage_module.main(args, args["devices"], args["options"])


@pytest.mark.skipif(os.getuid() != 0, reason="test must run as root")
def test_write_device_integration(tmp_path, stage_module):
    tree = tmp_path / "tree"
    args = create_args(tree)
    # ensure we have a ramdisk
    subprocess.check_call(["modprobe", "brd"])
    test_blk_device = "/dev/ram7"
    if open(test_blk_device, "br").read(512) != b'\x00' * 512:
        pytest.skip(f"block device {test_blk_device} not empty")
    args["devices"]["device"]["path"] = test_blk_device
    # ensure we have a test file
    test_input_file = tree / "test-input.txt"
    test_input_file.write_text("test-data")
    args["options"]["from"] = "input://tree/test-input.txt"

    with contextlib.ExitStack() as cm:
        cm.callback(
            subprocess.check_call,
            ["dd", "if=/dev/zero", f"of={test_blk_device}", "bs=512", "count=1"],
        )

        stage_module.main(args, args["devices"], args["options"])

        assert open(test_blk_device, "rb").read(128) == b"test-data" + b'\x00' * 119
