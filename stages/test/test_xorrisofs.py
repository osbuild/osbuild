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
        inputs,
        tmp_path,
        {
            "boot": {
                "image": "images/eltorito.img",
                "catalog": "boot.cat",
            },
            "filename": "test.iso",
            "volid": "test",
            "efi": "images/efiboot.img",
        },
    )

    mock_run.assert_called_with([
        "/usr/bin/xorrisofs",
        "-verbose",
        "-V", "test",
        "-b", "images/eltorito.img",
        "-c", "boot.cat",
        "--boot-catalog-hide",
        "-boot-load-size", "4",
        "-boot-info-table",
        "-no-emul-boot",
        "-rock",
        "-joliet",
        "-eltorito-alt-boot",
        "-e", "images/efiboot.img",
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
        inputs,
        tmp_path,
        {
            "boot": {
                "image": "images/eltorito.img",
                "catalog": "boot.cat",
            },
            "grub2mbr": "/usr/lib/grub/i386-pc/boot_hybrid.img",
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
        "--grub2-mbr", "/usr/lib/grub/i386-pc/boot_hybrid.img",
        "-partition_offset", "16",
        "-appended_part_as_gpt",
        "-append_partition", "2", "C12A7328-F81F-11D2-BA4B-00A0C93EC93B", os.path.join(fake_input_tree, "images/efiboot.img"),
        "-iso_mbr_part_type", "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
        "-b", "images/eltorito.img",
        "-c", "boot.cat",
        "--boot-catalog-hide",
        "-no-emul-boot",
        "-boot-load-size", "4",
        "-boot-info-table",
        "--grub2-boot-info",
        "-eltorito-alt-boot",
        "-e", "--interval:appended_partition_2:all::",
        "-no-emul-boot",
        "-o", os.path.join(tmp_path, "test.iso"),
        fake_input_tree,
    ], check=True)
