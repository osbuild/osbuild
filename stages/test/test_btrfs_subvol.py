#!/usr/bin/python3

import contextlib
import os
import subprocess

import pytest

from osbuild.testutil import has_executable

STAGE_NAME = "org.osbuild.btrfs.subvol"


def make_btrfs_disk(tmp_path):
    fake_disk_path = tmp_path / "fake.img"
    with fake_disk_path.open("w") as fp:
        fp.truncate(110 * 1024 * 1024)
    subprocess.run(["mkfs.btrfs", fake_disk_path], check=True)
    return fake_disk_path


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
@pytest.mark.skipif(not has_executable("mkfs.btrfs"), reason="need mkfs.btrfs")
def test_btrfs_subvol_integration(tmp_path, stage_module):
    fake_disk_path = make_btrfs_disk(tmp_path)
    fake_disk_mnt = tmp_path / "mnt"
    fake_disk_mnt.mkdir()
    with contextlib.ExitStack() as cm:
        subprocess.run(["mount", fake_disk_path, fake_disk_mnt], check=True)
        cm.callback(subprocess.run, ["umount", fake_disk_mnt], check=True)

        paths = {
            "mounts": fake_disk_mnt,
        }
        options = {
            "subvolumes": [
                {"name": "/asubvol"},
                {"name": "/subvols/root"},
            ],
        }
        stage_module.main(paths, options)

        output = subprocess.check_output([
            "btrfs", "subvolume", "list", fake_disk_mnt], encoding="utf-8")
        assert "path asubvol\n" in output
        assert "path subvols/root\n" in output
