#!/usr/bin/python3
import os
import subprocess
from unittest.mock import call, patch

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


@patch("subprocess.run")
def test_grub2_partition_mocked(mocked_run, tmp_path, stage_module):
    options = {
        "filename": "disk.img",
        "platform": "some-platform",
        "location": 0,
        "core": {
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

    output_path = ""

    def mock_side_effect(args, **_):
        """
        Intercept the args to subprocess.run() to leak the random output path and create the file that's expected by the
        shutil.copy() in the stage's main().
        """
        nonlocal output_path
        output_path = args[args.index("--output") + 1]
        with open(output_path, "wb") as fake_image_file:
            fake_image_file.write(b"I am a grub core image")

    mocked_run.side_effect = mock_side_effect

    stage_module.main(tmp_path, options)

    assert os.path.basename(output_path) == "grub2-core.img"
    assert mocked_run.call_args_list == [
        call(["grub2-mkimage", "--verbose",
              "--directory", "/usr/lib/grub/some-platform",
              "--prefix", "(,gpt1)/boot/",
              "--format", "some-platform",
              "--compression", "auto",
              "--output", output_path,
              "part_gpt", "ext2"], check=True),
    ]
