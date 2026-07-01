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
def mock_efi_binaries(stage_module, tmp_path):
    efidir = str(tmp_path / "efi_tmp")
    os.makedirs(os.path.join(efidir, "BOOT"), exist_ok=True)
    os.makedirs(os.path.join(efidir, "redhat"), exist_ok=True)
    shim_path = os.path.join(efidir, "BOOT", "BOOTAA64.EFI")
    grub_path = os.path.join(efidir, "redhat", "grubaa64.efi")
    with open(shim_path, "wb") as f:
        f.write(b"fake_shim")
    with open(grub_path, "wb") as f:
        f.write(b"fake_grub")
    with patch.object(stage_module, "find_efi_binaries") as mock:
        mock.return_value = (shim_path, grub_path, "redhat", efidir)
        yield mock


@pytest.fixture
def mock_loop_client():
    client = MagicMock()

    @contextlib.contextmanager
    def _fake_device(_path):
        yield "/dev/loop99"
    client.device = MagicMock(side_effect=_fake_device)
    return client


@pytest.mark.usefixtures("mock_efi_binaries")
@pytest.mark.parametrize("inputs,options,expected_cmd_parts", [
    # Basic test - kernel + initramfs only
    (
        FAKE_INPUTS,
        {"filename": "test.bfb"},
        [
            "/usr/bin/mlx-mkbfb",
            "--ramdisk",
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
            "--boot-path",
            "--boot-desc",
            "/lib/firmware/mellanox/boot/default.bfb",
        ]
    ),
])
@patch("subprocess.run")
@patch("os.path.getsize", return_value=1024)
def test_bfb_command_generation(
        _mock_getsize,
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

    # The last subprocess.run call should be mlx-mkbfb
    actual_cmd = mock_run.call_args_list[-1][0][0]

    for part in expected_cmd_parts:
        assert part in actual_cmd, f"Expected {part!r} in command: {actual_cmd}"
    assert f"{output_dir}/{options['filename']}" in actual_cmd


@pytest.mark.usefixtures("mock_efi_binaries")
@patch("subprocess.run")
@patch("os.path.getsize", return_value=1024)
def test_bfb_rootfs_combination(_mock_getsize, mock_run, tmp_path, mock_loop_client, stage_module):
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


@pytest.mark.usefixtures("mock_efi_binaries")
@patch("subprocess.run")
@patch("os.path.getsize", return_value=1024)
def test_bfb_no_rootfs(_mock_getsize, mock_run, tmp_path, mock_loop_client, stage_module):
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


def test_find_efi_source_paths_new(tmp_path, stage_module):
    """Test EFI discovery with BootLoaderUpdatesPhase1 paths"""
    efi_grub = tmp_path / "usr/lib/efi/grub/1.0/EFI"
    efi_shim = tmp_path / "usr/lib/efi/shim/1.0/EFI"
    efi_grub.mkdir(parents=True)
    efi_shim.mkdir(parents=True)

    result = stage_module.find_efi_source_paths(str(tmp_path))
    assert len(result) == 2


def test_find_efi_source_paths_legacy(tmp_path, stage_module):
    """Test EFI discovery falling back to legacy bootupd path"""
    legacy = tmp_path / "usr/lib/bootupd/updates/EFI"
    legacy.mkdir(parents=True)
    result = stage_module.find_efi_source_paths(str(tmp_path))
    assert len(result) == 1
    assert result[0].endswith("usr/lib/bootupd/updates/EFI")


def test_find_efi_source_paths_boot_efi(tmp_path, stage_module):
    """Test EFI discovery falling back to /boot/efi/EFI"""
    boot_efi = tmp_path / "boot/efi/EFI"
    boot_efi.mkdir(parents=True)
    result = stage_module.find_efi_source_paths(str(tmp_path))
    assert len(result) == 1
    assert result[0].endswith("boot/efi/EFI")


def test_find_efi_source_paths_none(tmp_path, stage_module):
    """Test EFI discovery raises when no paths found"""
    with pytest.raises(ValueError, match="No EFI source paths found"):
        stage_module.find_efi_source_paths(str(tmp_path))


def test_find_efi_vendor_dir_name(tmp_path, stage_module):
    """Test vendor directory discovery"""
    (tmp_path / "BOOT").mkdir()
    (tmp_path / "redhat").mkdir()

    result = stage_module.find_efi_vendor_dir_name(str(tmp_path))
    assert result == "redhat"


def test_find_efi_vendor_dir_name_fedora(tmp_path, stage_module):
    """Test vendor directory discovery for Fedora"""
    (tmp_path / "BOOT").mkdir()
    (tmp_path / "fedora").mkdir()

    result = stage_module.find_efi_vendor_dir_name(str(tmp_path))
    assert result == "fedora"


def test_find_efi_binaries(tmp_path, stage_module):
    """Test end-to-end EFI binary discovery"""
    # Set up legacy EFI path structure
    efi_dir = tmp_path / "usr/lib/bootupd/updates/EFI"
    boot_dir = efi_dir / "BOOT"
    vendor_dir = efi_dir / "redhat"
    boot_dir.mkdir(parents=True)
    vendor_dir.mkdir(parents=True)

    (boot_dir / "BOOTAA64.EFI").write_bytes(b"shim")
    (vendor_dir / "grubaa64.efi").write_bytes(b"grub")

    shim, grub, vendor, efidir = stage_module.find_efi_binaries(str(tmp_path))
    assert os.path.basename(shim) == "BOOTAA64.EFI"
    assert os.path.basename(grub) == "grubaa64.efi"
    assert vendor == "redhat"
    assert os.path.isdir(efidir)
