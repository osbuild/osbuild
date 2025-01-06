#!/usr/bin/python3
import os
import subprocess

import pytest

STAGE_NAME = "org.osbuild.grub2.inst"


# pylint: disable=inconsistent-return-statements
def find_grub_mkimage():
    for exe in ["grub2-mkimage", "grub-mkimage"]:
        try:
            subprocess.check_call([exe, "-V"])
            return exe
        except FileNotFoundError:
            pass
    pytest.skip("cannot find grub{,2}-mkimage")


def test_grub2_partition(tmp_path, stage_module):
    treedir = tmp_path / "tree"
    os.makedirs(treedir, exist_ok=True)
    with open(treedir / "disk.img", "wb") as f:
        f.write(b"Just testing")

    options = {
        "filename": "disk.img",
        "platform": "i386-pc",
        "location": 0,
        "core": {
            "binary": find_grub_mkimage(),
            "type": "mkimage",
            "partlabel": "gpt",
            "filesystem": "ext4",
        },
        "prefix": {
            "type": "partition",
            "partlabel": "gpt",
            "number": 0,
            "path": "/boot/",
        },
    }
    stage_module.main(treedir, options)

    # Make sure the test string is overwritten
    with open(treedir / "disk.img", "rb") as f:
        msg = f.read(12)
        assert msg != b"Just testing"


def test_grub2_iso9660(tmp_path, stage_module):
    treedir = tmp_path / "tree"
    os.makedirs(treedir, exist_ok=True)

    options = {
        "filename": "eltorito.img",
        "platform": "i386-pc",
        "core": {
            "binary": find_grub_mkimage(),
            "type": "mkimage",
            "partlabel": "gpt",
            "filesystem": "iso9660",
        },
        "prefix": {
            "path": "/boot/grub2/",
        },
    }
    stage_module.main(treedir, options)
    assert os.path.exists(treedir / "eltorito.img")
