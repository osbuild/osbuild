#!/usr/bin/python3

import copy
import unittest.mock
from unittest.mock import patch

import pytest

STAGE_NAME = "org.osbuild.bfb"


@pytest.fixture(name="mocked_temp_dir")
def mocked_temp_dir_fixture(tmp_path):
    with patch("tempfile.TemporaryDirectory") as mock_temp_dir:
        mock_temp_dir.return_value.__enter__.return_value = str(tmp_path)
        yield tmp_path


FAKE_INPUTS = {
    "kernel": {
        "path": "/input/kernel/path",
        "data": {
            "files": {
                "kernel-file": {}
            }
        }
    },
    "initramfs": {
        "path": "/input/initramfs/path",
        "data": {
            "files": {
                "initramfs-file": {}
            }
        }
    }
}

FAKE_INPUTS_WITH_ROOTFS = {
    **FAKE_INPUTS,
    "rootfs": {
        "path": "/input/rootfs/path",
        "data": {
            "files": {
                "rootfs-file": {}
            }
        }
    }
}


@pytest.mark.parametrize("inputs,options,expected_cmd_parts", [
    # Basic test - kernel + initramfs only
    (
        FAKE_INPUTS,
        {"filename": "test.bfb"},
        [
            "/usr/bin/mlx-mkbfb",
            "--image", "/input/kernel/path/kernel-file",
            "--initramfs", "/input/initramfs/path/initramfs-file",
            "--capsule", "/lib/firmware/mellanox/boot/capsule/boot_update2.cap",
            "--boot-args-v0", "--boot-args-v2",
            "/lib/firmware/mellanox/boot/default.bfb",
        ]
    ),
    # Test with rootfs (should use combined file)
    (
        FAKE_INPUTS_WITH_ROOTFS,
        {"filename": "test.bfb"},
        [
            "/usr/bin/mlx-mkbfb",
            "--image", "/input/kernel/path/kernel-file",
            "--initramfs",  # Will be combined.img path
            "--capsule", "/lib/firmware/mellanox/boot/capsule/boot_update2.cap",
            "--boot-args-v0", "--boot-args-v2",
            "/lib/firmware/mellanox/boot/default.bfb",
        ]
    ),
])
@patch("subprocess.run")
@patch("builtins.open", new_callable=unittest.mock.mock_open)
def test_bfb_command_generation(
        _mock_file,
        mock_run,
        stage_module,
        inputs,
        options,
        expected_cmd_parts):
    """Test that stage generates correct mlx-mkbfb command"""

    output_dir = "/fake/output"

    # Deep copy to prevent parse_input()'s popitem() from mutating shared test data
    stage_module.main(copy.deepcopy(inputs), output_dir, options)

    mock_run.assert_called_once()
    actual_cmd = mock_run.call_args[0][0]

    for part in expected_cmd_parts:
        assert part in actual_cmd, f"Expected {part!r} in command: {actual_cmd}"
    assert f"{output_dir}/{options['filename']}" in actual_cmd


@patch("subprocess.run")
def test_bfb_rootfs_combination(mock_run, mocked_temp_dir, stage_module):
    """Test that initramfs and rootfs are combined when rootfs is provided"""

    options = {"filename": "test.bfb"}
    output_dir = str(mocked_temp_dir)

    with patch("builtins.open", unittest.mock.mock_open(read_data=b"fake_data")) as mock_file:
        stage_module.main(copy.deepcopy(FAKE_INPUTS_WITH_ROOTFS), output_dir, options)

    mock_file.assert_called()
    mock_run.assert_called_once()

    actual_cmd = mock_run.call_args[0][0]
    initramfs_idx = actual_cmd.index("--initramfs") + 1
    initramfs_path = actual_cmd[initramfs_idx]
    assert "combined.img" in initramfs_path


def test_parse_input(stage_module):
    """Test the parse_input helper function"""

    test_inputs = {
        "test": {
            "path": "/test/path",
            "data": {
                "files": {
                    "testfile": {}
                }
            }
        }
    }

    result = stage_module.parse_input(test_inputs, "test")
    assert result == "/test/path/testfile"
