#!/usr/bin/python3

import contextlib
import os
import subprocess

import pytest  # type: ignore

from osbuild.testutil import has_executable

STAGE_NAME = "org.osbuild.mkdir"


def test_mkdir(tmp_path, stage_module):
    tree = tmp_path / "tree"
    tree.mkdir()

    options = {
        "paths": [
            {"path": "/fake_dir"},
            {"path": "fake_relative_dir"}
        ]
    }
    args = {
        "tree": f"{tree}",
        "options": options
    }
    stage_module.main(args)
    assert (tree / "fake_dir").exists()
    assert (tree / "fake_relative_dir").exists()


def test_mkdir_on_a_tree(tmp_path, stage_module):
    tree = tmp_path / "tree"
    tree.mkdir()

    options = {
        "paths": [
            {
                "path": "tree:///fake_parent/fake_dir",
                "parents": 1
            }
        ]
    }
    args = {
        "tree": f"{tree}",
        "options": options
    }
    stage_module.main(args)
    assert (tree / "fake_parent/fake_dir").exists()


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
@pytest.mark.skipif(not has_executable("mkfs.ext4"), reason="need mkfs.ext4")
def test_mkdir_on_a_mount(tmp_path, stage_module):
    tree = tmp_path / "tree"
    tree.mkdir()

    # Create fake EXT4 disk image
    fake_disk_path = tmp_path / "fake.img"
    with fake_disk_path.open("w") as fp:
        fp.truncate(10 * 1024 * 1024)
    subprocess.run(
        ["mkfs.ext4", os.fspath(fake_disk_path)], check=True)

    fake_disk_mnt = tmp_path / "mounts"
    fake_disk_mnt.mkdir()

    with contextlib.ExitStack() as cm:
        subprocess.run(["mount", fake_disk_path, fake_disk_mnt], check=True)
        cm.callback(subprocess.run, ["umount", fake_disk_mnt], check=True)

        options = {
            "paths": [
                {
                    "path": "mount:///fake_parent/fake_dir",
                    "parents": 1
                }
            ]
        }
        args = {
            "tree": f"{tree}",
            "options": options,
            "paths": {
                "mounts": fake_disk_mnt,
            }
        }
        stage_module.main(args)
        assert (fake_disk_mnt / "fake_parent/fake_dir").exists()
