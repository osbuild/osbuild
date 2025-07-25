#!/usr/bin/python3

import os.path
from unittest.mock import call, patch

import pytest

STAGE_NAME = "org.osbuild.grub2.iso"

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

### BEGIN /etc/grub.d/10_linux ###
menuentry 'Install Fedora 42' --class fedora --class gnu-linux --class gnu --class os {
	linux /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=Fedora-42-Everything-x86_64 quiet
	initrd /images/pxeboot/initrd.img
}
menuentry 'Test this media & install Fedora 42' --class fedora --class gnu-linux --class gnu --class os {
	linux /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=Fedora-42-Everything-x86_64 rd.live.check quiet
	initrd /images/pxeboot/initrd.img
}
"""

CONFIG_PART_2 = """
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


@patch("shutil.copy2")
@pytest.mark.parametrize("test_data,expected_conf", [
    # default
    ({}, CONFIG_PART_1 + CONFIG_PART_2),
    # fips menu enable
    ({"fips": True}, CONFIG_PART_1 + CONFIG_FIPS + CONFIG_PART_2),
    # default to menu entry 1
    ({"config": {"default": 1}}, CONFIG_DEFAULT + CONFIG_PART_1 + CONFIG_PART_2)
])
def test_grub2_iso(mocked_copy2, tmp_path, stage_module, test_data, expected_conf):
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

    stage_module.main(treedir, options)

    assert os.path.exists(confpath)
    assert confpath.read_text() == expected_conf
    assert mocked_copy2.call_args_list == [
        call("/boot/efi/EFI/fedora/shimx64.efi", os.fspath(efidir / "BOOTX64.EFI")),
        call("/boot/efi/EFI/fedora/mmx64.efi", os.fspath(efidir / "mmx64.efi")),
        call("/boot/efi/EFI/fedora/gcdx64.efi", os.fspath(efidir / "grubx64.efi")),
        call("/usr/share/grub/unicode.pf2", os.fspath(efidir / "fonts"))
    ]


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
