#!/usr/bin/python3

import os.path
from unittest.mock import call, patch

import pytest

STAGE_NAME = "org.osbuild.grub2.iso.legacy"

CONFIG_PART_1 = """
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
"""

CONFIG_PART_TEST = """
menuentry 'Test this media & install Fedora-IoT 41' --class fedora --class gnu-linux --class gnu --class os {
	linux /images/pxeboot/vmlinuz inst.ks=hd:LABEL=Fedora-41-X86_64:/install.ks rd.live.check quiet
	initrd /images/pxeboot/initrd.img
}
"""

CONFIG_PART_TROUBLESHOOTING = """

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

CONFIG_FIPS = """
menuentry 'Install Fedora-IoT 41 in FIPS mode' --class fedora --class gnu-linux --class gnu --class os {
	linux /images/pxeboot/vmlinuz inst.ks=hd:LABEL=Fedora-41-X86_64:/install.ks quiet fips=1
	initrd /images/pxeboot/initrd.img
}
"""

CONFIG_DEFAULT = """set default="1"
"""


@patch("shutil.copytree")
@pytest.mark.parametrize("test_data,expected_conf", [
    # default
    ({}, CONFIG_PART_1 + CONFIG_PART_TEST + CONFIG_PART_TROUBLESHOOTING),
    # fips menu enable
    ({"fips": True}, CONFIG_PART_1 + CONFIG_PART_TEST + CONFIG_FIPS + CONFIG_PART_TROUBLESHOOTING),
    # default to menu entry 1
    ({"config": {"default": 1, "timeout": 10}}, CONFIG_DEFAULT + CONFIG_PART_1 + CONFIG_PART_TEST + CONFIG_PART_TROUBLESHOOTING),
    # no troubleshooting
    ({"troubleshooting": False}, CONFIG_PART_1 + CONFIG_PART_TEST + "\n\n"),
])
def test_grub2_iso_legacy_smoke(mocked_copytree, tmp_path, stage_module, test_data, expected_conf):
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
    options.update(test_data)

    stage_module.main(treedir, options)

    assert os.path.exists(confpath)
    assert confpath.read_text() == expected_conf
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
                "default": 1
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
