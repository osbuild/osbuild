#!/usr/bin/python3

import os
from unittest import mock

from osbuild.testutil import make_fake_input_tree

STAGE_NAME = "org.osbuild.xorrisofs"


@mock.patch("subprocess.run")
def test_xorrisofs_syslinux_efi_from_tree(mock_run, tmp_path, stage_module):
    fake_input_tree = make_fake_input_tree(tmp_path, {})

    inputs = {
        "tree": {
            "path": fake_input_tree,
        }
    }

    # default (syslinux)
    stage_module.main(
        {
            "inputs": inputs,
            "tree": tmp_path,
        },
        {
            "filename": "test.iso",
            "volid": "test",
            "efi": "images/efiboot.img",
        },
    )

    mock_run.assert_called_with([
        "/usr/bin/xorrisofs",
        "-verbose",
        "-V", "test",
        "-rock",
        "-joliet",
        "-eltorito-alt-boot",
        "-e", os.path.join(fake_input_tree, "images/efiboot.img"),
        "-no-emul-boot",
        "-o", os.path.join(tmp_path, "test.iso"),
        fake_input_tree,
    ], check=True)


@mock.patch("subprocess.run")
def test_xorrisofs_grub2_efi_from_tree(mock_run, tmp_path, stage_module):
    fake_input_tree = make_fake_input_tree(tmp_path, {})

    inputs = {
        "tree": {
            "path": fake_input_tree,
        }
    }

    stage_module.main(
        {
            "inputs": inputs,
            "tree": tmp_path,
        },
        {
            "grub2mbr": True,
            "filename": "test.iso",
            "volid": "test",
            "efi": "images/efiboot.img",
        },
    )

    mock_run.assert_called_with([
        "/usr/bin/xorrisofs",
        "-verbose",
        "-rock",
        "-joliet",
        "-V", "test",
        "--grub2-mbr", True,
        "-partition_offset", "16",
        "-appended_part_as_gpt",
        "-append_partition", "2", "C12A7328-F81F-11D2-BA4B-00A0C93EC93B", os.path.join(fake_input_tree, "images/efiboot.img"),
        "-iso_mbr_part_type", "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
        "-no-emul-boot",
        "-o", os.path.join(tmp_path, "test.iso"),
        fake_input_tree,
    ], check=True)


@mock.patch("subprocess.run")
def test_xorrisofs_syslinux_efi_from_input(mock_run, tmp_path, stage_module):
    fake_input_tree = make_fake_input_tree(tmp_path, {})
    fake_input_tree_efi = make_fake_input_tree(tmp_path, {}, name="efi")

    inputs = {
        "tree": {
            "path": fake_input_tree,
        },
        "efi": {
            "path": fake_input_tree_efi,
        }
    }

    # default (syslinux)
    stage_module.main(
        {
            "inputs": inputs,
            "tree": tmp_path,
        },
        {
            "filename": "test.iso",
            "volid": "test",
            "efi": "input://efi/efiboot.img",
        },
    )

    mock_run.assert_called_with([
        "/usr/bin/xorrisofs",
        "-verbose",
        "-V", "test",
        "-rock",
        "-joliet",
        "-eltorito-alt-boot",
        "-e", os.path.join(fake_input_tree_efi, "efiboot.img"),
        "-no-emul-boot",
        "-o", os.path.join(tmp_path, "test.iso"),
        fake_input_tree,
    ], check=True)


@mock.patch("subprocess.run")
def test_xorrisofs_grub2_efi_from_input(mock_run, tmp_path, stage_module):
    fake_input_tree = make_fake_input_tree(tmp_path, {})
    fake_input_tree_efi = make_fake_input_tree(tmp_path, {}, name="efi")

    inputs = {
        "tree": {
            "path": fake_input_tree,
        },
        "efi": {
            "path": fake_input_tree_efi,
        }
    }

    stage_module.main(
        {
            "inputs": inputs,
            "tree": tmp_path,
        },
        {
            "grub2mbr": True,
            "filename": "test.iso",
            "volid": "test",
            "efi": "input://efi/efiboot.img",
        },
    )

    mock_run.assert_called_with([
        "/usr/bin/xorrisofs",
        "-verbose",
        "-rock",
        "-joliet",
        "-V", "test",
        "--grub2-mbr", True,
        "-partition_offset", "16",
        "-appended_part_as_gpt",
        "-append_partition", "2", "C12A7328-F81F-11D2-BA4B-00A0C93EC93B", os.path.join(fake_input_tree_efi, "efiboot.img"),
        "-iso_mbr_part_type", "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
        "-no-emul-boot",
        "-o", os.path.join(tmp_path, "test.iso"),
        fake_input_tree,
    ], check=True)
