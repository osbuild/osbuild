#
# Test for the util.lvm2 module
#

import json
import os
import subprocess
import time
import uuid
from tempfile import TemporaryDirectory
from typing import List

import pytest

from osbuild import loop
from osbuild.util import lvm2
from osbuild.util.types import PathLike

from ..test import TestBase


def have_lvm() -> bool:
    try:
        r = subprocess.run(
            ["vgs"],
            encoding="utf8",
            stdout=subprocess.PIPE,
            check=False
        )
    except FileNotFoundError:
        return False
    return r.returncode == 0


@pytest.fixture(name="tempdir")
def tempdir_fixture():
    with TemporaryDirectory(prefix="lvm2-") as tmp:
        yield tmp


def make_loop(ctl, fd: int, offset, sizelimit, sector_size=512):
    if not sizelimit:
        stat = os.fstat(fd)
        sizelimit = stat.st_size - offset
        print(f"size: {sizelimit}")
    else:
        sizelimit *= sector_size

    return ctl.loop_for_fd(fd, offset, sizelimit=sizelimit, autoclear=True)


def pvcreate(path: PathLike):
    cmd = ["pvcreate", os.fspath(path)]
    subprocess.run(cmd, check=True)


def vgcreate(path: PathLike, vg_name: str):
    cmd = ["vgcreate", vg_name, os.fspath(path)]
    subprocess.run(cmd, check=True)


def lvcreate(vg_name, name: str, size: str):
    cmd = [
        "lvcreate", "-an",
        "-l", size,
        "-n", name,
        vg_name
    ]
    subprocess.run(cmd, check=True)


def list_vgs():
    cmd = [
        "vgs",
        "--reportformat", "json",
        "--readonly",
        "-o", "+vg_all"
    ]

    res = subprocess.run(cmd,
                         check=False,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         encoding="UTF-8")

    data = res.stdout.strip()

    if res.returncode != 0:
        msg = f"vgs: {res.stderr.strip()}"
        raise RuntimeError(msg)

    data = json.loads(data)

    return data["report"][0]["vg"]


def find_vg(lst: List, name: str):
    for vg in lst:
        if vg["vg_name"] == name:
            return vg
    return None


@pytest.mark.skipif(not have_lvm(), reason="require lvm2 installation")
@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_rename_vg_group(tempdir):

    path = os.path.join(tempdir, "lvm.img")
    ctl = loop.LoopControl()

    f = None
    lo = None
    try:
        f = open(path, "wb+")
        f.truncate(100 * 1024 * 1024)
        f.flush()
        lo = make_loop(ctl, f.fileno(), 0, None)
        devname = os.path.join("/dev", lo.devname)

        vg_name = str(uuid.uuid4())
        pvcreate(devname)
        vgcreate(devname, vg_name)
        lvcreate(vg_name, "lv1", r"100%FREE")

        vgs = list_vgs()
        vg = find_vg(vgs, vg_name)
        assert vg

    finally:
        if lo:
            lo.close()
        if f:
            f.close()

    new_name = str(uuid.uuid4())
    with lvm2.Disk.open(path) as disk:
        assert disk.metadata
        assert disk.metadata.vg_name == vg_name

        disk.rename_vg(new_name)
        disk.creation_host = "osbuild"
        disk.description = "created via lvm2 and osbuild"

        disk.flush_metadata()

    f = None
    lo = None
    try:
        f = open(path, "rb")
        lo = make_loop(ctl, f.fileno(), 0, None)
        devname = os.path.join("/dev", lo.devname)

        vg = None
        for i in range(3):
            vgs = list_vgs()
            vg = find_vg(vgs, new_name)
            if vg:
                break
            time.sleep(0.250 * (i + 1))
        if not vg:
            raise RuntimeError(f"Could not find vg {new_name}")
    finally:
        if lo:
            lo.close()
        if f:
            f.close()
