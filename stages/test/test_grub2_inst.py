#!/usr/bin/python3
import os

STAGE_NAME = "org.osbuild.grub2.inst"

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
