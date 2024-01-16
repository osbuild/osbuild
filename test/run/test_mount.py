#!/usr/bin/python3

#
# Runtime Tests for Device Host Services
#

import errno
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from contextlib import contextmanager

import pytest

from osbuild import devices, host, meta, mounts, testutil

from ..test import TestBase


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
def make_dev_tmpfs(tmp_path):
    dev_path = os.path.join(tmp_path, "dev")
    os.makedirs(dev_path)
    subprocess.run(["mount", "-t", "tmpfs", "-o", "nosuid", "none", dev_path], check=True)
    yield dev_path
    subprocess.run(["umount", "--lazy", dev_path], check=True)


def create_image(tmp_path):
    # create a file to contain an image
    tree = os.path.join(tmp_path, "tree")
    os.makedirs(tree)
    size = 2 * 1024 * 1024
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
            "volid": "7B7795E7",
            "fat-size": 32
        }
    }

    with make_arguments(mkfsopts):
        env = os.environ.copy()
        env["PYTHONPATH"] = os.curdir
        subprocess.run(
            [os.path.join(os.curdir, "stages", "org.osbuild.mkfs.fat")],
            env=env,
            check=True,
            stdout=sys.stdout,
            stderr=sys.stderr)
    return tree, size


def mount(mgr, devpath, tree, size, mountpoint, options):
    index = meta.Index(os.curdir)
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
            index.get_module_info("Mount", "org.osbuild.fat"),
            dev,
            None,
            "/",
            options
        )
    )


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_without_options(tmp_path):
    tree, size = create_image(tmp_path)
    options = {}

    with tempfile.TemporaryDirectory(dir=tmp_path) as mountpoint:
        with host.ServiceManager() as mgr:
            with make_dev_tmpfs(tmp_path) as devpath:
                mount(mgr, devpath, tree, size, mountpoint, options)
                with open(os.path.join(mountpoint, "test"), "w", encoding="utf-8") as f:
                    f.write("should work")
                os.remove(os.path.join(mountpoint, "test"))


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_all_options(tmp_path):
    tree, size = create_image(tmp_path)
    options = {
        "readonly": True,
        "uid": 0,
        "gid": 0,
        "umask": "077",
        "shortname": "winnt"
    }
    print(options)

    with tempfile.TemporaryDirectory(dir=tmp_path) as mountpoint:
        with host.ServiceManager() as mgr:
            with make_dev_tmpfs(tmp_path) as devpath:
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


def create_image_with_partitions(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    img = tree / "disk.img"
    with img.open("w") as fp:
        fp.truncate(20 * 1024 * 1024)
    for cmd in [
        ["parted", "--script", img, "mklabel", "msdos"],
        ["parted", "--script", img, "mkpart", "primary", "ext4", "1MiB", "10Mib"],
        ["parted", "--script", img, "mkpart", "primary", "ext4", "10MiB", "19Mib"],
        ["mkfs.ext4", "-F", "-E", f"offset={1*1024*1024}", img, "9M"],
        ["mkfs.ext4", "-F", "-E", f"offset={10*1024*1024}", img, "9M"],
    ]:
        subprocess.check_call(cmd)
    return tree, img.name


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
@pytest.mark.skipif(not testutil.has_executable("parted"), reason="no parted executable")
def test_mount_with_partition(tmp_path):
    tree, img_name = create_image_with_partitions(tmp_path)

    # need root of the sourcecode to find the stages/mounts etc
    src_root = pathlib.Path(__file__).parent.parent.parent
    index = meta.Index(src_root)
    loopback_mod_info = index.get_module_info("Device", "org.osbuild.loopback")
    ext4_mod_info = index.get_module_info("Mount", "org.osbuild.ext4")

    with host.ServiceManager() as mgr:
        with make_dev_tmpfs(tmp_path) as devpath:
            devmgr = devices.DeviceManager(mgr, devpath, tree)
            opts = {
                "filename": img_name,
                "partscan": True,
            }
            dev = devices.Device("loop", loopback_mod_info, None, opts)
            device_node_path = os.path.join(devpath, devmgr.open(dev)["path"])

            mnt_base = tmp_path / "mntbase"
            mntmgr = mounts.MountManager(devmgr, mnt_base)
            opts = {}
            # mount both partitions
            for i in range(1, 3):
                mount_opts = mounts.Mount(
                    name=f"name-{i}", info=ext4_mod_info, device=dev,
                    partition=i, target=f"/mnt-{i}", options=opts)
                mntmgr.mount(mount_opts)

            # check that the both mounts actually happend
            output = subprocess.check_output(
                ["lsblk", "--json", device_node_path],
                encoding="utf8",
            ).strip()
            lsblk_info = json.loads(output)
            assert len(lsblk_info["blockdevices"][0]["children"]) == 2
            chld = lsblk_info["blockdevices"][0]["children"]
            assert chld[0]["mountpoints"] == [f"{mnt_base}/mnt-1"]
            assert chld[1]["mountpoints"] == [f"{mnt_base}/mnt-2"]
