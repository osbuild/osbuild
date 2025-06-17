#!/usr/bin/python3

import os.path

import pytest

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


# Test that the /etc/default/grub file is created with the correct content
@pytest.mark.parametrize("test_data,kernel_opts,expected_conf,expected_boot_conf", [
    # default
    ({}, "", """GRUB_CMDLINE_LINUX=""
GRUB_TIMEOUT=0
GRUB_ENABLE_BLSCFG=true
""",
        """
set timeout=0

# load the grubenv file
load_env

# selection of the next boot entry via variables 'next_entry' and
# `saved_entry` present in the 'grubenv' file. Both variables are
# set by grub tools, like grub2-reboot, grub2-set-default

if [ "${next_entry}" ] ; then
   set default="${next_entry}"
   set next_entry=
   save_env next_entry
   set boot_once=true
else
   set default="${saved_entry}"
fi

search --no-floppy --set=root --label root
set boot=${root}
function load_video {
  insmod all_video
}
${serial}${terminal_input}${terminal_output}
blscfg
"""),
    # custom
    ({
        "default": "0",
        "timeout": 10,
        "terminal_input": ["console"],
        "terminal_output": ["serial"],
        "serial": "serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1",
    }, "", """GRUB_CMDLINE_LINUX=""
GRUB_TIMEOUT=10
GRUB_ENABLE_BLSCFG=true
GRUB_SERIAL_COMMAND="serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1"
GRUB_TERMINAL_INPUT="console"
GRUB_TERMINAL_OUTPUT="serial"
GRUB_DEFAULT=0
""",
        """
set timeout=10

# load the grubenv file
load_env

# selection of the next boot entry via variables 'next_entry' and
# `saved_entry` present in the 'grubenv' file. Both variables are
# set by grub tools, like grub2-reboot, grub2-set-default

if [ "${next_entry}" ] ; then
   set default="${next_entry}"
   set next_entry=
   save_env next_entry
   set boot_once=true
else
   set default="${saved_entry}"
fi

search --no-floppy --set=root --label root
set boot=${root}
function load_video {
  insmod all_video
}

serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1
terminal_input console
terminal_output serial
blscfg
"""),
    # custom (Azure)
    ({
        "default": "saved",
        "disable_submenu": True,
        "disable_recovery": True,
        "distributor": "$(sed 's, release .*$,,g' /etc/system-release)",
        "serial": "serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1",
        "terminal": ["serial", "console"],
        "terminal_output": ["console"],
        "timeout": 10,
        "timeout_style": "countdown",
    },
        "loglevel=3 crashkernel=auto console=tty1 console=ttyS0 earlyprintk=ttyS0 rootdelay=300",
        """GRUB_CMDLINE_LINUX="loglevel=3 crashkernel=auto console=tty1 console=ttyS0 earlyprintk=ttyS0 rootdelay=300"
GRUB_TIMEOUT=10
GRUB_ENABLE_BLSCFG=true
GRUB_DISABLE_RECOVERY=true
GRUB_DISABLE_SUBMENU=true
GRUB_DISTRIBUTOR="$(sed 's, release .*$,,g' /etc/system-release)"
GRUB_SERIAL_COMMAND="serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1"
GRUB_TERMINAL="serial console"
GRUB_TERMINAL_OUTPUT="console"
GRUB_TIMEOUT_STYLE=countdown
GRUB_DEFAULT=saved
""",
        """
set timeout=10

# load the grubenv file
load_env

# selection of the next boot entry via variables 'next_entry' and
# `saved_entry` present in the 'grubenv' file. Both variables are
# set by grub tools, like grub2-reboot, grub2-set-default

if [ "${next_entry}" ] ; then
   set default="${next_entry}"
   set next_entry=
   save_env next_entry
   set boot_once=true
else
   set default="${saved_entry}"
fi

search --no-floppy --set=root --label root
set boot=${root}
function load_video {
  insmod all_video
}

serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1${terminal_input}
terminal_output console
blscfg
"""),
])
def test_grub2_default_conf(tmp_path, stage_module, test_data, kernel_opts, expected_conf, expected_boot_conf):
    treedir = tmp_path / "tree"
    confpath = treedir / "etc/default/grub"
    confpath.parent.mkdir(parents=True, exist_ok=True)
    bootconfpath = treedir / "boot/grub2/grub.cfg"

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
    options["kernel_opts"] = kernel_opts
    stage_module.main(treedir, options)

    assert os.path.exists(confpath)
    assert confpath.read_text() == expected_conf

    assert os.path.exists(bootconfpath)
    assert bootconfpath.read_text() == expected_boot_conf


# Test that the /etc/default/grub file is created with the correct content
@pytest.mark.parametrize("test_data,kernel_opts,expected_conf,expected_boot_conf", [
    # default
    ({}, "", """GRUB_CMDLINE_LINUX=""
GRUB_TIMEOUT=0
GRUB_ENABLE_BLSCFG=true
""",
        """
set timeout=0

# load the grubenv file
load_env

# selection of the next boot entry via variables 'next_entry' and
# `saved_entry` present in the 'grubenv' file. Both variables are
# set by grub tools, like grub2-reboot, grub2-set-default

if [ "${next_entry}" ] ; then
   set default="${next_entry}"
   set next_entry=
   save_env next_entry
   set boot_once=true
else
   set default="${saved_entry}"
fi

search --no-floppy --set=root --label root
set boot=${root}
function load_video {
  insmod all_video
}

blscfg
"""),
    # custom
    ({
        "default": "0",
        "timeout": 10,
        "terminal_input": ["console"],
        "terminal_output": ["serial"],
        "serial": "serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1",
    }, "", """GRUB_CMDLINE_LINUX=""
GRUB_TIMEOUT=10
GRUB_ENABLE_BLSCFG=true
GRUB_SERIAL_COMMAND="serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1"
GRUB_TERMINAL_INPUT="console"
GRUB_TERMINAL_OUTPUT="serial"
GRUB_DEFAULT=0
""",
        """
set timeout=10

# load the grubenv file
load_env

# selection of the next boot entry via variables 'next_entry' and
# `saved_entry` present in the 'grubenv' file. Both variables are
# set by grub tools, like grub2-reboot, grub2-set-default

if [ "${next_entry}" ] ; then
   set default="${next_entry}"
   set next_entry=
   save_env next_entry
   set boot_once=true
else
   set default="${saved_entry}"
fi

search --no-floppy --set=root --label root
set boot=${root}
function load_video {
  insmod all_video
}

serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1
terminal_input console
terminal_output serial
blscfg
"""),
    # custom (Azure)
    ({
        "default": "saved",
        "disable_submenu": True,
        "disable_recovery": True,
        "distributor": "$(sed 's, release .*$,,g' /etc/system-release)",
        "serial": "serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1",
        "terminal": ["serial", "console"],
        "terminal_output": ["console"],
        "timeout": 10,
        "timeout_style": "countdown",
    },
        "loglevel=3 crashkernel=auto console=tty1 console=ttyS0 earlyprintk=ttyS0 rootdelay=300",
        """GRUB_CMDLINE_LINUX="loglevel=3 crashkernel=auto console=tty1 console=ttyS0 earlyprintk=ttyS0 rootdelay=300"
GRUB_TIMEOUT=10
GRUB_ENABLE_BLSCFG=true
GRUB_DISABLE_RECOVERY=true
GRUB_DISABLE_SUBMENU=true
GRUB_DISTRIBUTOR="$(sed 's, release .*$,,g' /etc/system-release)"
GRUB_SERIAL_COMMAND="serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1"
GRUB_TERMINAL="serial console"
GRUB_TERMINAL_OUTPUT="console"
GRUB_TIMEOUT_STYLE=countdown
GRUB_DEFAULT=saved
""",
        """
set timeout=10

# load the grubenv file
load_env

# selection of the next boot entry via variables 'next_entry' and
# `saved_entry` present in the 'grubenv' file. Both variables are
# set by grub tools, like grub2-reboot, grub2-set-default

if [ "${next_entry}" ] ; then
   set default="${next_entry}"
   set next_entry=
   save_env next_entry
   set boot_once=true
else
   set default="${saved_entry}"
fi

search --no-floppy --set=root --label root
set boot=${root}
function load_video {
  insmod all_video
}

serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1
terminal_output console
blscfg
"""),
])
def test_grub2_default_conf_v2(tmp_path, stage_module, test_data, kernel_opts, expected_conf, expected_boot_conf):
    treedir = tmp_path / "tree"
    confpath = treedir / "etc/default/grub"
    confpath.parent.mkdir(parents=True, exist_ok=True)
    bootconfpath = treedir / "boot/grub2/grub.cfg"

    options = {
        "compat_version": 2,
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
        ],
    }

    options["config"] = test_data
    options["kernel_opts"] = kernel_opts
    stage_module.main(treedir, options)

    assert os.path.exists(confpath)
    assert confpath.read_text() == expected_conf

    assert os.path.exists(bootconfpath)
    assert bootconfpath.read_text() == expected_boot_conf
