#!/usr/bin/python3

#
# Runtime Tests for Device Host Services
#

import errno
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager

import pytest

from osbuild import devices, host, meta, mounts

from ..test import TestBase


@pytest.fixture(name="tmpdir")
def tmpdir_fixture():
    with tempfile.TemporaryDirectory(prefix="test-devices-") as tmp:
        yield tmp


@contextmanager
def make_arguments(opts):
    os.mkdir("/run/osbuild/api")
    with open("/run/osbuild/api/arguments", "w", encoding="utf-8") as f:
        json.dump(opts, f)
    try:
        yield
    finally:
        os.remove("/run/osbuild/api/arguments")
        os.rmdir("/run/osbuild/api")


@contextmanager
def make_dev_tmpfs(tmpdir):
    dev_path = os.path.join(tmpdir, "dev")
    os.makedirs(dev_path)
    subprocess.run(["mount", "-t", "tmpfs", "-o", "nosuid", "none", dev_path], check=True)
    yield dev_path
    subprocess.run(["umount", "--lazy", dev_path], check=True)


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_mount_ro(tmpdir):
    index = meta.Index(os.curdir)

    # create a file to contain an image
    tree = os.path.join(tmpdir, "tree")
    os.makedirs(tree)
    size = 1024 * 1024
    file = os.path.join(tree, "image.img")
    with open(file, "wb") as f:
        f.truncate(size)

    # Create an FS in the image
    mkfsopts = {
        "devices": {
            "device": {
                "path": file
            }
        },
        "options": {
            "label": "TEST",
            "uuid": "FEEDFACE-CAFE-4004-FEED-C0DEC0FFEE11"
        }
    }
    with make_arguments(mkfsopts):
        subprocess.run(
            [os.path.join(os.curdir, "stages",  "org.osbuild.mkfs.ext4")],
            check=True,
            stdout=sys.stdout,
            stderr=sys.stderr)

    with tempfile.TemporaryDirectory() as mountpoint:
        with host.ServiceManager() as mgr:
            with make_dev_tmpfs(tmpdir) as devpath:
                # Device manager to open the loopback device
                devmgr = devices.DeviceManager(mgr, devpath, tree)
                # get a Device for the loopback
                dev = devices.Device(
                    "loop",
                    index.get_module_info(
                        "Device",
                        "org.osbuild.loopback"
                    ),
                    None,
                    {
                        "filename": "image.img",
                        "start": 0,
                        "size": size // 512  # size is in sectors / blocks
                    }
                )
                # open the device and get its loopback path
                lpath = os.path.join(
                    devpath,
                    devmgr.open(dev)["path"]
                )
                # mount the loopback
                mounts.MountManager(
                    devmgr,
                    mountpoint
                ).mount(
                    mounts.Mount(
                        lpath,
                        index.get_module_info("Mount", "org.osbuild.ext4"),
                        dev,
                        "/",
                        {"readonly": True}
                    )
                )

                # try to write in it, and failure to do so is a success
                with pytest.raises(OSError) as err:
                    with open(os.path.join(mountpoint, "test"), "w", encoding="utf-8") as f:
                        f.write("should not work")
                assert err.value.errno == errno.EROFS  # Check that FS is read only
