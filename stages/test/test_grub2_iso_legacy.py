#!/usr/bin/python3

import os.path
from unittest.mock import call, patch

import pytest

STAGE_NAME = "org.osbuild.grub2.iso.legacy"

expected_grub_cfg = """
set default="1"

function load_video {
  insmod all_video
}

load_video
set gfxpayload=keep
insmod gzio
insmod part_gpt
insmod ext2
insmod chain

set timeout=10
### END /etc/grub.d/00_header ###

search --no-floppy --set=root -l 'Fedora-41-X86_64'

### BEGIN /etc/grub.d/10_linux ###
menuentry 'Install Fedora-IoT 41' --class fedora --class gnu-linux --class gnu --class os {
	linux /images/pxeboot/vmlinuz inst.ks=hd:LABEL=Fedora-41-X86_64:/install.ks quiet
	initrd /images/pxeboot/initrd.img
}
menuentry 'Test this media & install Fedora-IoT 41' --class fedora --class gnu-linux --class gnu --class os {
	linux /images/pxeboot/vmlinuz inst.ks=hd:LABEL=Fedora-41-X86_64:/install.ks rd.live.check quiet
	initrd /images/pxeboot/initrd.img
}
submenu 'Troubleshooting -->' {
	menuentry 'Install Fedora-IoT 41 in basic graphics mode' --class fedora --class gnu-linux --class gnu --class os {
		linux /images/pxeboot/vmlinuz inst.ks=hd:LABEL=Fedora-41-X86_64:/install.ks nomodeset quiet
		initrd /images/pxeboot/initrd.img
	}
	menuentry 'Rescue a Fedora-IoT system' --class fedora --class gnu-linux --class gnu --class os {
		linux /images/pxeboot/vmlinuz inst.ks=hd:LABEL=Fedora-41-X86_64:/install.ks inst.rescue quiet
		initrd /images/pxeboot/initrd.img
	}
	menuentry 'Boot first drive' --class fedora --class gnu-linux --class gnu --class os {
		chainloader (hd0)+1
	}
}
"""


@patch("shutil.copytree")
def test_grub2_iso_legacy_smoke(mocked_copytree, tmp_path, stage_module):
    treedir = tmp_path / "tree"
    confpath = treedir / "boot/grub2/grub.cfg"
    confpath.parent.mkdir(parents=True, exist_ok=True)

    # from fedora-ostree-bootiso-xz.json
    options = {
        "product": {
            "name": "Fedora-IoT",
            "version": "41"
        },
        "isolabel": "Fedora-41-X86_64",
        "kernel": {
            "dir": "/images/pxeboot",
            "opts": [
                "inst.ks=hd:LABEL=Fedora-41-X86_64:/install.ks"
            ]
        },
        "config": {
            "timeout": 10,
        }
    }

    stage_module.main(treedir, options)

    assert os.path.exists(confpath)
    assert confpath.read_text() == expected_grub_cfg
    assert mocked_copytree.call_args_list == [
        call("/usr/lib/grub/i386-pc", os.fspath(treedir / "boot/grub2/i386-pc"),
             dirs_exist_ok=True),
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
