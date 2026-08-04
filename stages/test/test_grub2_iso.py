#!/usr/bin/python3

import glob
import os.path
import shutil
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from osbuild.testutil import make_fake_tree

STAGE_NAME = "org.osbuild.grub2.iso"

# Real layout from Fedora 44+
EFI_LAYOUT_USR_LIB = {
    "usr/lib/efi/grub2/1:2.12-60.fc44/EFI/fedora/grubx64.efi": "grubx64",
    "usr/lib/efi/grub2/1:2.12-60.fc44/EFI/fedora/gcdx64.efi": "gcdx64",
    "usr/lib/efi/shim/16.1-5/EFI/BOOT/BOOTX64.EFI": "bootx64",
    "usr/lib/efi/shim/16.1-5/EFI/BOOT/fbx64.efi": "fbx64",
    "usr/lib/efi/shim/16.1-5/EFI/fedora/BOOTX64.CSV": "csv",
    "usr/lib/efi/shim/16.1-5/EFI/fedora/mmx64.efi": "mmx64",
    "usr/lib/efi/shim/16.1-5/EFI/fedora/shim.efi": "shim",
    "usr/lib/efi/shim/16.1-5/EFI/fedora/shimx64.efi": "shimx64",
    "usr/share/grub/unicode.pf2": "font",
}

EFI_LAYOUT_LEGACY = {
    "boot/efi/EFI/fedora/shimx64.efi": "shimx64",
    "boot/efi/EFI/fedora/mmx64.efi": "mmx64",
    "boot/efi/EFI/fedora/gcdx64.efi": "gcdx64",
    "usr/share/grub/unicode.pf2": "font",
}


@contextmanager
def fake_host_root(host_root):
    """Redirect absolute EFI/font paths into a temporary host root."""
    prefixes = ("/usr/lib/efi", "/boot/efi", "/usr/share/grub")
    real_glob = glob.glob
    real_exists = os.path.exists
    real_isdir = os.path.isdir
    real_copy2 = shutil.copy2

    def remap(path):
        path = os.fspath(path)
        if path.startswith(prefixes):
            return os.fspath(host_root / path.lstrip("/"))
        return path

    def patched_glob(pathname, **kwargs):
        return real_glob(remap(pathname), **kwargs)

    def patched_exists(path):
        return real_exists(remap(path))

    def patched_isdir(path):
        return real_isdir(remap(path))

    def patched_copy2(src, dst, *args, **kwargs):
        return real_copy2(remap(src), dst, *args, **kwargs)

    with patch("glob.glob", patched_glob), \
            patch("os.path.exists", patched_exists), \
            patch("os.path.isdir", patched_isdir), \
            patch("shutil.copy2", patched_copy2):
        yield


CONFIG_PART_1 = """
function load_video {
  insmod efi_gop
  insmod efi_uga
  insmod video_bochs
  insmod video_cirrus
  insmod all_video
}

load_video
set gfxpayload=keep
insmod gzio
insmod part_gpt
insmod ext2

set timeout=60
### END /etc/grub.d/00_header ###

search --no-floppy --set=root -l 'Fedora-42-Everything-x86_64'

"""

CONFIG_TMPL_CUSTOM = """
menuentry '{name}' --class fedora --class gnu-linux --class gnu --class os {{
	linux {linux}
	initrd {initrd}
}}"""

CONFIG_PART_INSTALL = """
menuentry 'Install Fedora 42' --class fedora --class gnu-linux --class gnu --class os {
	linux /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=Fedora-42-Everything-x86_64 quiet
	initrd /images/pxeboot/initrd.img
}
"""

CONFIG_PART_TEST = """
menuentry 'Test this media & install Fedora 42' --class fedora --class gnu-linux --class gnu --class os {
	linux /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=Fedora-42-Everything-x86_64 rd.live.check quiet
	initrd /images/pxeboot/initrd.img
}
"""

CONFIG_PART_TROUBLESHOOTING = """

submenu 'Troubleshooting -->' {
	menuentry 'Install Fedora 42 in basic graphics mode' --class fedora --class gnu-linux --class gnu --class os {
		linux /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=Fedora-42-Everything-x86_64 nomodeset quiet
		initrd /images/pxeboot/initrd.img
	}
	menuentry 'Rescue a Fedora system' --class fedora --class gnu-linux --class gnu --class os {
		linux /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=Fedora-42-Everything-x86_64 inst.rescue quiet
		initrd /images/pxeboot/initrd.img
	}
}
"""

CONFIG_FIPS = """
menuentry 'Install Fedora 42 in FIPS mode' --class fedora --class gnu-linux --class gnu --class os {
	linux /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=Fedora-42-Everything-x86_64 quiet fips=1
	initrd /images/pxeboot/initrd.img
}
"""

CONFIG_DEFAULT = """set default="1"
"""


@pytest.mark.parametrize("test_data,expected_conf", [
    # default
    ({}, CONFIG_PART_1 + "\n" + CONFIG_PART_INSTALL + CONFIG_PART_TEST + CONFIG_PART_TROUBLESHOOTING),
    # fips menu enable
    ({"fips": True}, CONFIG_PART_1 + "\n" + CONFIG_PART_INSTALL +
     CONFIG_PART_TEST + CONFIG_FIPS + CONFIG_PART_TROUBLESHOOTING),
    # default to menu entry 1
    ({"config": {"default": 1}}, CONFIG_DEFAULT + CONFIG_PART_1 + "\n" +
     CONFIG_PART_INSTALL + CONFIG_PART_TEST + CONFIG_PART_TROUBLESHOOTING),
    # no troubleshooting
    ({"troubleshooting": False}, CONFIG_PART_1 + "\n" + CONFIG_PART_INSTALL + CONFIG_PART_TEST + "\n\n"),
    # only install
    ({"troubleshooting": False, "test": False}, CONFIG_PART_1 + "\n" + CONFIG_PART_INSTALL + "\n\n\n"),
    # nothing
    ({"troubleshooting": False, "test": False, "install": False}, CONFIG_PART_1 + "\n\n\n\n\n"),
    # custom entries
    (
        {
            "kernel": {
                "dir": "/images/pxeboot",
                "opts": [
                    "root=hd:LABEL=root",
                    "rhgb"
                ]
            },
            "troubleshooting": False,
            "test": False,
            "install": False,
            "custom": [
                {
                    "name": "label 0",
                    "linux": "/foo/bar root=baz quiet",
                    "initrd": "/foo/bar",
                },
                {
                    "name": "label 1",
                    "linux": "/bar/foo root=baz quiet",
                    "initrd": "/bar/foo",
                },
                {
                    "name": "label 2",
                    "linux": "${kernelpath} ${root}",
                    "initrd": "${initrdpath}",
                },
            ]
        },
        CONFIG_PART_1 +
        CONFIG_TMPL_CUSTOM.format(
            name="label 0",
            linux="/foo/bar root=baz quiet",
            initrd="/foo/bar",
        ) +
        CONFIG_TMPL_CUSTOM.format(
            name="label 1",
            linux="/bar/foo root=baz quiet",
            initrd="/bar/foo",
        ) +
        CONFIG_TMPL_CUSTOM.format(
            name="label 2",
            linux="/images/pxeboot/vmlinuz root=hd:LABEL=root rhgb",
            initrd="/images/pxeboot/initrd.img",
        ) +
        "\n\n\n\n\n",
    ),
])
def test_grub2_iso(tmp_path, stage_module, test_data, expected_conf):
    host = tmp_path / "host"
    make_fake_tree(host, EFI_LAYOUT_USR_LIB)

    treedir = tmp_path / "tree"
    treedir.mkdir(parents=True, exist_ok=True)
    efidir = treedir / "EFI/BOOT"
    confpath = efidir / "grub.cfg"

    # from fedora-ostree-bootiso-xz.json
    options = {
        "product": {
            "name": "Fedora",
            "version": "42"
        },
        "kernel": {
            "dir": "/images/pxeboot",
            "opts": [
                "inst.stage2=hd:LABEL=Fedora-42-Everything-x86_64"
            ]
        },
        "isolabel": "Fedora-42-Everything-x86_64",
        "architectures": [
            "X64"
        ],
        "vendor": "fedora"
    }
    options.update(test_data)

    with fake_host_root(host):
        stage_module.main(treedir, options)

    assert os.path.exists(confpath)
    assert confpath.read_text() == expected_conf
    assert (efidir / "BOOTX64.EFI").read_text() == "shimx64"
    assert (efidir / "mmx64.efi").read_text() == "mmx64"
    assert (efidir / "grubx64.efi").read_text() == "gcdx64"
    assert (efidir / "fonts/unicode.pf2").read_text() == "font"


def test_grub2_iso_legacy_boot_efi(tmp_path, stage_module):
    host = tmp_path / "host"
    make_fake_tree(host, EFI_LAYOUT_LEGACY)

    treedir = tmp_path / "tree"
    treedir.mkdir(parents=True, exist_ok=True)
    efidir = treedir / "EFI/BOOT"

    options = {
        "product": {
            "name": "Fedora",
            "version": "42"
        },
        "kernel": {
            "dir": "/images/pxeboot",
            "opts": [
                "inst.stage2=hd:LABEL=Fedora-42-Everything-x86_64"
            ]
        },
        "isolabel": "Fedora-42-Everything-x86_64",
        "architectures": [
            "X64"
        ],
        "vendor": "fedora",
        "troubleshooting": False,
        "test": False,
        "install": False,
    }

    with fake_host_root(host):
        stage_module.main(treedir, options)

    assert (efidir / "BOOTX64.EFI").read_text() == "shimx64"
    assert (efidir / "mmx64.efi").read_text() == "mmx64"
    assert (efidir / "grubx64.efi").read_text() == "gcdx64"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    (
        {}, ["'isolabel' is a required property", "'kernel' is a required property", "'product' is a required property"]
    ),
    (
        {
            "isolabel": "an-isolabel",
            "product": {
                "name": "a-name",
                "version": "a-version",
            },
            "kernel": {},
        }, ["'dir' is a required property"],
    ),
    (
        {
            "isolabel": "an-isolabel",
            "product": {},
            "kernel": {
                "dir": "/path/to",
            },
        }, ["'name' is a required property", "'version' is a required property"],
    ),
    # good
    (
        {
            "isolabel": "an-isolabel",
            "product": {
                "name": "a-name",
                "version": "a-version",
            },
            "kernel": {
                "dir": "/path/to",
            },
        }, "",
    ),
    # good + fips
    (
        {
            "isolabel": "an-isolabel",
            "product": {
                "name": "a-name",
                "version": "a-version",
            },
            "kernel": {
                "dir": "/path/to",
            },
            "fips": True,
        }, "",
    ),
    # good + default
    (
        {
            "isolabel": "an-isolabel",
            "product": {
                "name": "a-name",
                "version": "a-version",
            },
            "kernel": {
                "dir": "/path/to",
            },
            "config": {
                "default": 1,
            }
        }, "",
    ),
])
def test_schema_validation(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": {},
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        err_msgs = sorted([e.as_dict()["message"] for e in res.errors])
        assert err_msgs == expected_err
