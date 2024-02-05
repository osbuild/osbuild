#!/usr/bin/python3

import os
import textwrap
from unittest.mock import patch

from osbuild.testutil import make_fake_tree

STAGE_NAME = "org.osbuild.zipl.inst"


@patch("subprocess.run")
def test_zipl_inst_default(mocked_run, tmp_path, stage_module):
    make_fake_tree(tmp_path, {
        "/boot/loader/entries/ostree-1-fedora-coreos.conf": textwrap.dedent("""\
        title Fedora CoreOS 39.20240206.dev.0 (ostree:0)
        version 1
        options ignition.platform.id=qemu ostree=/ostree/boot.1/fedora-coreos/abcd/0
        linux /vmlinuz-6.6.14-200.fc39.s390x
        initrd /initramfs-6.6.14-200.fc39.s390x.img
        """),
        "/vmlinuz-6.6.14-200.fc39.s390x": "fake-vmlinuz",
        "/initramfs-6.6.14-200.fc39.s390x.img": "fake-initramfs.img",
    })
    fake_paths = {
        "mounts": os.fspath(tmp_path),
        "devices": "/run/osbuild/dev",
    }
    fake_devices = {
        "disk": {
            "path": "some-device-path",
        }
    }
    fake_options = {
        "kernel": "1",
        "location": "some-location",
    }

    stage_module.main(fake_paths, fake_devices, fake_options)
    assert len(mocked_run.call_args_list) == 1
    args, kwargs = mocked_run.call_args_list[0]
    assert len(args) == 1
    run_argv = args[0]
    assert "ignition.platform.id=qemu ostree=/ostree/boot.1/fedora-coreos/abcd/0" in run_argv
    assert kwargs["check"]


@patch("subprocess.run")
def test_zipl_inst_kernel_opts_append(mocked_run, tmp_path, stage_module):
    make_fake_tree(tmp_path, {
        "/boot/loader/entries/00_linux.conf": textwrap.dedent("""\
        title fake-linux
        linux /vmlinuz
        initrd /initrd.img
        options root=/dev/sda1 ro
        version 6.8
        """),
        "/vmlinuz": "fake-vmlinuz",
        "/initrd.img": "fake-initrd.img",
    })
    fake_paths = {
        "mounts": os.fspath(tmp_path),
        "devices": "/run/osbuild/dev",
    }
    fake_devices = {
        "disk": {
            "path": "some-device-path",
        }
    }
    fake_options = {
        "kernel": "6.8",
        "location": "some-location",
        "kernel_opts_append": ["some=more", "opts"],
    }

    stage_module.main(fake_paths, fake_devices, fake_options)
    assert len(mocked_run.call_args_list) == 1
    args, kwargs = mocked_run.call_args_list[0]
    assert len(args) == 1
    run_argv = args[0]
    assert "root=/dev/sda1 ro some=more opts" in run_argv
    assert kwargs["check"]
