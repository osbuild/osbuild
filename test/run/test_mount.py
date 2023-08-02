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
    os.makedirs("/run/osbuild/api")
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


def create_image(tmpdir):
    # create a file to contain an image
    tree = os.path.join(tmpdir, "tree")
    os.makedirs(tree)
    size = 2 * 1024 * 1024
    file = os.path.join(tree, "image.img")
    with open(file, "wb") as f:
        f.truncate(size)

    # Create an FS in the image
    mkfsopts = {
        "devices": {"device": {"path": file}},
        "options": {"label": "TEST", "volid": "7B7795E7", "fat-size": 32},
    }

    with make_arguments(mkfsopts):
        env = os.environ.copy()
        env["PYTHONPATH"] = os.curdir
        subprocess.run(
            [os.path.join(os.curdir, "stages", "org.osbuild.mkfs.fat")],
            env=env,
            check=True,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
    return tree, size


def mount(mgr, devpath, tree, size, mountpoint, options):
    index = meta.Index(os.curdir)
    # Device manager to open the loopback device
    devmgr = devices.DeviceManager(mgr, devpath, tree)
    # get a Device for the loopback
    dev = devices.Device(
        "loop",
        index.get_module_info("Device", "org.osbuild.loopback"),
        None,
        {"filename": "image.img", "start": 0, "size": size // 512},  # size is in sectors / blocks
    )
    # open the device and get its loopback path
    lpath = os.path.join(devpath, devmgr.open(dev)["path"])
    # mount the loopback
    mounts.MountManager(devmgr, mountpoint).mount(
        mounts.Mount(lpath, index.get_module_info("Mount", "org.osbuild.fat"), dev, "/", options)
    )


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_without_options(tmpdir):
    tree, size = create_image(tmpdir)
    options = {}

    with tempfile.TemporaryDirectory(dir=tmpdir) as mountpoint:
        with host.ServiceManager() as mgr:
            with make_dev_tmpfs(tmpdir) as devpath:
                mount(mgr, devpath, tree, size, mountpoint, options)
                with open(os.path.join(mountpoint, "test"), "w", encoding="utf-8") as f:
                    f.write("should work")
                os.remove(os.path.join(mountpoint, "test"))


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_all_options(tmpdir):
    tree, size = create_image(tmpdir)
    options = {"readonly": True, "uid": 0, "gid": 0, "umask": "077", "shortname": "winnt"}
    print(options)

    with tempfile.TemporaryDirectory(dir=tmpdir) as mountpoint:
        with host.ServiceManager() as mgr:
            with make_dev_tmpfs(tmpdir) as devpath:
                mount(mgr, devpath, tree, size, mountpoint, options)

                # Check FS is read only
                with pytest.raises(OSError) as err:
                    with open(os.path.join(mountpoint, "test"), "w", encoding="utf-8") as f:
                        f.write("should not work")
                assert err.value.errno == errno.EROFS

                # Check the other options
                st = os.lstat(mountpoint)
                assert st.st_mode == 0o040700
                assert st.st_uid == 0
                assert st.st_gid == 0

                shortname_tested = False
                proc = subprocess.run("mount", stdout=subprocess.PIPE, check=True)
                for line in proc.stdout.splitlines():
                    strline = line.decode("utf-8")
                    if mountpoint in strline:
                        assert "winnt" in strline
                        shortname_tested = True
                assert shortname_tested
