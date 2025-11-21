#!/usr/bin/python3

import os.path

from osbuild.testutil import make_fake_tree

STAGE_NAME = "org.osbuild.ostree.grub2"


def test_ostree_grub2_boot(tmp_path, stage_module):
    make_fake_tree(tmp_path, {
        "ostree/boot.1/default/b6cdf47cafd171e003c001802f1829ad39e20f7177d6e27401aba73efb71be22/0": "",
        "grub.cfg": "linux /vmlinux ostree=@OSTREE@"
    })

    inputs = {
        "tree": {
            "path": tmp_path
        }
    }

    options = {
        "filename": "grub.cfg"
    }
    stage_module.main({
        "inputs": inputs,
        "tree": tmp_path,
        "options": options,
    })

    confpath = tmp_path / "grub.cfg"
    assert os.path.exists(confpath)
    assert confpath.read_text() == "linux /vmlinux ostree=ostree/boot.1/default/b6cdf47cafd171e003c001802f1829ad39e20f7177d6e27401aba73efb71be22/0"
