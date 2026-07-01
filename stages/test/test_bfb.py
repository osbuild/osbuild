#!/usr/bin/python3
# pylint: disable=redefined-outer-name

import contextlib
import copy
import os
from unittest.mock import MagicMock, patch

import pytest

STAGE_NAME = "org.osbuild.bfb"


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


@pytest.fixture
def mock_makeefi(stage_module):
    def fake_mkefidir(efidir, source_tree):  # pylint: disable=unused-argument
        os.makedirs(os.path.join(efidir, "BOOT"), exist_ok=True)

    def fake_mkefiboot(efidir, output_efiboot_img, loop_client):  # pylint: disable=unused-argument
        with open(output_efiboot_img, "wb") as f:
            f.write(b"fake_efiboot")

    with patch.object(stage_module.makeefi, "mkefidir",
                      side_effect=fake_mkefidir), \
            patch.object(stage_module.makeefi, "mkefiboot",
                         side_effect=fake_mkefiboot):
        yield


@pytest.fixture
def mock_loop_client():
    client = MagicMock()

    @contextlib.contextmanager
    def _fake_device(_path):
        yield "/dev/loop99"
    client.device = MagicMock(side_effect=_fake_device)
    return client


@pytest.mark.usefixtures("mock_makeefi")
@pytest.mark.parametrize("inputs,options,expected_cmd_parts", [
    # Basic test - kernel + initramfs only
    (
        FAKE_INPUTS,
        {"filename": "test.bfb"},
        [
            "/usr/bin/mlx-mkbfb",
            "--ramdisk",
            "--capsule",
            "--boot-path",
            "--boot-desc",
            "/lib/firmware/mellanox/boot/default.bfb",
        ]
    ),
    # Test with rootfs
    (
        FAKE_INPUTS_WITH_ROOTFS,
        {"filename": "test.bfb"},
        [
            "/usr/bin/mlx-mkbfb",
            "--ramdisk",
            "--capsule",
            "--boot-path",
            "--boot-desc",
            "/lib/firmware/mellanox/boot/default.bfb",
        ]
    ),
])
@patch("subprocess.run")
def test_bfb_command_generation(
        mock_run,
        tmp_path,
        stage_module,
        mock_loop_client,
        inputs,
        options,
        expected_cmd_parts):
    """Test that stage generates correct mlx-mkbfb command"""

    output_dir = str(tmp_path / "output")
    os.makedirs(output_dir)

    # Create fake input files so file I/O works
    test_inputs = copy.deepcopy(inputs)
    for name in test_inputs:
        inp = test_inputs[name]
        files = inp["data"]["files"]
        fname = list(files.keys())[0]
        inp["path"] = str(tmp_path / name)
        os.makedirs(inp["path"], exist_ok=True)
        with open(os.path.join(inp["path"], fname), "wb") as f:
            f.write(b"fake")

    stage_module.main(test_inputs, output_dir, options, mock_loop_client)

    actual_cmd = mock_run.call_args_list[-1][0][0]

    for part in expected_cmd_parts:
        assert part in actual_cmd, f"Expected {part!r} in command: {actual_cmd}"
    assert f"{output_dir}/{options['filename']}" in actual_cmd


@pytest.mark.usefixtures("mock_makeefi")
@patch("subprocess.run")
def test_bfb_rootfs_combination(mock_run, tmp_path, mock_loop_client, stage_module):
    """Test that initramfs and rootfs are combined when rootfs is provided"""

    options = {"filename": "test.bfb"}
    output_dir = str(tmp_path / "output")
    os.makedirs(output_dir)

    test_inputs = copy.deepcopy(FAKE_INPUTS_WITH_ROOTFS)
    for name in test_inputs:
        inp = test_inputs[name]
        fname = list(inp["data"]["files"].keys())[0]
        inp["path"] = str(tmp_path / name)
        os.makedirs(inp["path"], exist_ok=True)
        with open(os.path.join(inp["path"], fname), "wb") as f:
            f.write(b"fake_data")

    stage_module.main(test_inputs, output_dir, options, mock_loop_client)

    # mlx-mkbfb is the last call
    actual_cmd = mock_run.call_args_list[-1][0][0]
    assert "--ramdisk" in actual_cmd


@pytest.mark.usefixtures("mock_makeefi")
@patch("subprocess.run")
def test_bfb_no_rootfs(mock_run, tmp_path, mock_loop_client, stage_module):
    """Test that initramfs is used directly when rootfs is not provided"""

    options = {"filename": "test.bfb"}
    output_dir = str(tmp_path / "output")
    os.makedirs(output_dir)

    test_inputs = copy.deepcopy(FAKE_INPUTS)
    for name in test_inputs:
        inp = test_inputs[name]
        fname = list(inp["data"]["files"].keys())[0]
        inp["path"] = str(tmp_path / name)
        os.makedirs(inp["path"], exist_ok=True)
        with open(os.path.join(inp["path"], fname), "wb") as f:
            f.write(b"fake_data")

    stage_module.main(test_inputs, output_dir, options, mock_loop_client)

    actual_cmd = mock_run.call_args_list[-1][0][0]
    assert "--ramdisk" in actual_cmd


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
