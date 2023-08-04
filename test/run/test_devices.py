#!/usr/bin/python3

#
# Runtime Tests for Device Host Services
#

import os
import tempfile

import pytest

from osbuild import loop, meta, service
from osbuild.service import device

from ..test import TestBase


@pytest.fixture(name="tmpdir")
def tmpdir_fixture():
    with tempfile.TemporaryDirectory(prefix="test-device-") as tmp:
        yield tmp


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_loopback_basic(tmpdir):
    index = meta.Index(os.curdir)
    info = index.get_module_info("Device", "org.osbuild.loopback")

    tree = os.path.join(tmpdir, "tree")
    os.makedirs(tree)

    devpath = os.path.join(tmpdir, "dev")
    os.makedirs(devpath)

    size = 1024 * 1024
    filename = os.path.join(tree, "image.img")
    with open(filename, "wb") as f:
        f.truncate(size)
        sb = os.fstat(f.fileno())

    testfile = os.path.join(tmpdir, "test.img")

    options = {
        "filename": "image.img",
        "start": 0,
        "size": size // 512  # size is in sectors / blocks
    }

    dev = device.Device("loop", info, None, options)

    with service.ServiceManager() as mgr:
        devmgr = device.DeviceManager(mgr, devpath, tree)
        reply = devmgr.open(dev)
        assert reply
        assert reply["path"]

        node = reply["path"]
        assert os.path.exists(os.path.join(devpath, node))

        minor = reply["node"]["minor"]
        lo = loop.Loop(minor)
        li = lo.get_status()

        assert li.lo_offset == 0
        assert li.lo_sizelimit == size
        assert li.lo_inode == sb.st_ino

        with pytest.raises(OSError):
            with open(testfile, "wb") as f:
                f.truncate(1)
                lo.configure(f.fileno())

        lo.close()

        uid = f"device/{dev.name}"
        client = mgr.services[uid]

        client.call("close", None)

        lo = loop.Loop(minor)
        with open(filename, "r", encoding="utf8") as f:
            assert not lo.is_bound_to(f.fileno())
