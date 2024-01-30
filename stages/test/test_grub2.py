#!/usr/bin/python3

from osbuild.testutil import make_fake_tree

STAGE_NAME = "org.osbuild.grub2"


def test_grub2_copy_efi_data(tmp_path, stage_module):
    fake_efi_src_dir = tmp_path / "fake-efi/EFI"
    make_fake_tree(fake_efi_src_dir, {
        "fedora/a.shim": "fake shim",
        "BOOT/BOOTX64.EFI": "I'm not real",
    })

    test_options = {
        "rootfs": {
            "label": "my-rootfs",
        },
        "uefi": {
            "install": True,
            "efi_src_dir": fake_efi_src_dir,
            "vendor": "fedora",
        },
    }
    fake_tree = tmp_path / "tree"
    stage_module.main(fake_tree, test_options)
    assert (fake_tree / "boot/efi/EFI/fedora/a.shim").exists()
    assert (fake_tree / "boot/efi/EFI/BOOT/BOOTX64.EFI").exists()
