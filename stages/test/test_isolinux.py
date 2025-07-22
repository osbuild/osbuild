#!/usr/bin/python3

import os.path
from unittest.mock import call, patch

import pytest

STAGE_NAME = "org.osbuild.isolinux"

CONFIG_PART_1 = """
default vesamenu.c32
timeout 600

display boot.msg

# Clear the screen when exiting the menu, instead of leaving the menu displayed.
# For vesamenu, this means the graphical background is still displayed without
# the menu itself for as long as the screen remains in graphics mode.
menu clear
menu background splash.png
menu title Fedora 42
menu vshift 8
menu rows 18
menu margin 8
#menu hidden
menu helpmsgrow 15
menu tabmsgrow 13

# Border Area
menu color border * #00000000 #00000000 none

# Selected item
menu color sel 0 #ffffffff #00000000 none

# Title bar
menu color title 0 #ff7ba3d0 #00000000 none

# Press [Tab] message
menu color tabmsg 0 #ff3a6496 #00000000 none

# Unselected menu item
menu color unsel 0 #84b8ffff #00000000 none

# Selected hotkey
menu color hotsel 0 #84b8ffff #00000000 none

# Unselected hotkey
menu color hotkey 0 #ffffffff #00000000 none

# Help text
menu color help 0 #ffffffff #00000000 none

# A scrollbar of some type? Not sure.
menu color scrollbar 0 #ffffffff #ff355594 none

# Timeout msg
menu color timeout 0 #ffffffff #00000000 none
menu color timeout_msg 0 #ffffffff #00000000 none

# Command prompt text
menu color cmdmark 0 #84b8ffff #00000000 none
menu color cmdline 0 #ffffffff #00000000 none

# Do not display the actual menu unless the user presses a key. All that is displayed is a timeout message.

menu tabmsg Press Tab for full configuration options on menu items.

menu separator # insert an empty line
menu separator # insert an empty line

label linux
  menu label ^Install Fedora 42
  kernel vmlinuz
  append initrd=initrd.img inst.stage2=hd:LABEL=Fedora-42-Everything-x86_64 quiet

label check
  menu label Test this ^media & install Fedora 42
  menu default
  kernel vmlinuz
  append initrd=initrd.img inst.stage2=hd:LABEL=Fedora-42-Everything-x86_64 rd.live.check quiet

"""

CONFIG_PART_2 = """
menu separator # insert an empty line

# utilities submenu
menu begin ^Troubleshooting
  menu title Troubleshooting Fedora 42

label basic
  menu indent count 5
  menu label Install using ^basic graphics mode
  text help
	Try this option out if you're having trouble installing
	Fedora 42.
  endtext
  kernel vmlinuz
  append initrd=initrd.img inst.stage2=hd:LABEL=Fedora-42-Everything-x86_64 nomodeset quiet
label rescue
  menu indent count 5
  menu label ^Rescue a Fedora system
  text help
	If the system will not boot, this lets you access files
	and edit config files to try to get it booting again.
  endtext
  kernel vmlinuz
  append initrd=initrd.img inst.stage2=hd:LABEL=Fedora-42-Everything-x86_64 inst.rescue quiet
label memtest
  menu label Run a ^memory test
  text help
	If your system is having issues, a problem with your
	system's memory may be the cause. Use this utility to
	see if the memory is working correctly.
  endtext
  kernel memtest

menu separator # insert an empty line

label local
  menu label Boot from ^local drive
  localboot 0xffff

menu separator # insert an empty line
menu separator # insert an empty line

label returntomain
  menu label Return to ^main menu
  menu exit

"""

CONFIG_FIPS = """
label fips
  menu label ^Install Fedora 42 in FIPS mode
  kernel vmlinuz
  append initrd=initrd.img inst.stage2=hd:LABEL=Fedora-42-Everything-x86_64 quiet fips=1

"""


@patch("os.link")
@patch("os.chmod")
@patch("shutil.copyfile")
@pytest.mark.parametrize("test_data,expected_conf", [
    # default
    ({}, CONFIG_PART_1 + CONFIG_PART_2),
    # fips menu enable
    ({"fips": True}, CONFIG_PART_1 + CONFIG_FIPS + CONFIG_PART_2)
])
def test_isolinux(mocked_copyfile, mocked_chmod, mocked_link, tmp_path, stage_module, test_data, expected_conf):
    treedir = tmp_path / "tree"
    treedir.mkdir(parents=True, exist_ok=True)
    datadir = tmp_path / "data"
    confpath = treedir / "isolinux/isolinux.cfg"

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
    }
    options.update(test_data)

    inputs = {
        "data": {
            "path": datadir
        }
    }

    stage_module.main(treedir, inputs, options)

    assert os.path.exists(confpath)
    assert confpath.read_text() == expected_conf
    assert mocked_copyfile.call_args_list == [
        call(os.fspath(datadir / "usr/share/anaconda/boot/syslinux-splash.png"),
             os.fspath(treedir / "isolinux/splash.png")),
        call(os.fspath(datadir / "usr/share/syslinux/isolinux.bin"),
             os.fspath(treedir / "isolinux/isolinux.bin")),
        call(os.fspath(datadir / "usr/share/syslinux/ldlinux.c32"),
             os.fspath(treedir / "isolinux/ldlinux.c32")),
        call(os.fspath(datadir / "usr/share/syslinux/libcom32.c32"),
             os.fspath(treedir / "isolinux/libcom32.c32")),
        call(os.fspath(datadir / "usr/share/syslinux/libutil.c32"),
             os.fspath(treedir / "isolinux/libutil.c32")),
        call(os.fspath(datadir / "usr/share/syslinux/vesamenu.c32"),
             os.fspath(treedir / "isolinux/vesamenu.c32")),
    ]
    assert mocked_chmod.call_args_list == [
        call(os.fspath(treedir / "isolinux/isolinux.bin"), 0o755),
        call(os.fspath(treedir / "isolinux/ldlinux.c32"), 0o755),
        call(os.fspath(treedir / "isolinux/libcom32.c32"), 0o755),
        call(os.fspath(treedir / "isolinux/libutil.c32"), 0o755),
        call(os.fspath(treedir / "isolinux/vesamenu.c32"), 0o755),
    ]
    assert mocked_link.call_args_list == [
        call(os.fspath(treedir / "images/pxeboot/vmlinuz"),
             os.fspath(treedir / "isolinux/vmlinuz")),
        call(os.fspath(treedir / "images/pxeboot/initrd.img"),
             os.fspath(treedir / "isolinux/initrd.img"))
    ]


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    (
        {}, ["'kernel' is a required property", "'product' is a required property"]
    ),
    (
        {
            "product": {
                "name": "a-name",
                "version": "a-version",
            },
            "kernel": {},
        }, ["'dir' is a required property"],
    ),
    (
        {
            "product": {},
            "kernel": {
                "dir": "/path/to",
            },
        }, ["'name' is a required property", "'version' is a required property"],
    ),
    # good
    (
        {
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
