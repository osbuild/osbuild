#!/usr/bin/python3

import os.path

import pytest

STAGE_NAME = "org.osbuild.grub2.legacy"


# Test that the /etc/default/grub file is created with the correct content
@pytest.mark.parametrize("test_data,expected_conf", [
    # default
    ({}, """GRUB_TIMEOUT=0
GRUB_CMDLINE_LINUX=""
GRUB_DISABLE_SUBMENU=true
GRUB_DISABLE_RECOVERY=true
GRUB_TIMEOUT_STYLE=countdown
GRUB_DEFAULT=saved
"""),
    # custom
    ({
        "disable_submenu": False,
        "disable_recovery": False,
        "timeout": 10,
        "timeout_style": "hidden",
    }, """GRUB_TIMEOUT=10
GRUB_CMDLINE_LINUX=""
GRUB_DISABLE_SUBMENU=false
GRUB_DISABLE_RECOVERY=false
GRUB_TIMEOUT_STYLE=hidden
GRUB_DEFAULT=saved
"""),
    # custom (Azure)
    ({
        "cmdline": "loglevel=3 crashkernel=auto console=tty1 console=ttyS0 earlyprintk=ttyS0 rootdelay=300",
        "disable_submenu": True,
        "disable_recovery": True,
        "distributor": "$(sed 's, release .*$,,g' /etc/system-release)",
        "serial": "serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1",
        "terminal": ["serial", "console"],
        "terminal_output": ["console"],
        "timeout": 10,
        "timeout_style": "countdown",
    }, """GRUB_TIMEOUT=10
GRUB_CMDLINE_LINUX="loglevel=3 crashkernel=auto console=tty1 console=ttyS0 earlyprintk=ttyS0 rootdelay=300"
GRUB_DISABLE_SUBMENU=true
GRUB_DISABLE_RECOVERY=true
GRUB_TIMEOUT_STYLE=countdown
GRUB_DEFAULT=saved
GRUB_DISTRIBUTOR="$(sed 's, release .*$,,g' /etc/system-release)"
GRUB_SERIAL_COMMAND="serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1"
GRUB_TERMINAL="serial console"
GRUB_TERMINAL_OUTPUT="console"
"""),
])
def test_grub2_default_conf(tmp_path, stage_module, test_data, expected_conf):
    treedir = tmp_path / "tree"
    confpath = treedir / "etc/default/grub"
    confpath.parent.mkdir(parents=True, exist_ok=True)

    options = {
        "rootfs": {
            "label": "root"
        },
        "entries": [
            {
                "id": "fff",
                "kernel": "4.18",
                "product": {
                    "name": "Fedora",
                    "version": "40"
                }
            }
        ]
    }

    options["config"] = test_data
    stage_module.main(treedir, options)

    assert os.path.exists(confpath)
    assert confpath.read_text() == expected_conf
