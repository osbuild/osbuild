#!/usr/bin/python3

import os.path

STAGE_NAME = "org.osbuild.grub2.legacy"


# Test that the /etc/default/grub file is created with the correct content
def test_grub2_default_conf(tmp_path, stage_module):
    treedir = tmp_path / "tree"
    confpath = treedir / "etc/default/grub"
    confpath.parent.mkdir(parents=True, exist_ok=True)

    options = {
        "rootfs": {
            "label": "root"
        },
        "entries": [
            {
                "id": "fff",
                "kernel": "4.18",
                "product": {
                    "name": "Fedora",
                    "version": "40"
                }
            }
        ]
    }

    stage_module.main(treedir, options)
    assert os.path.exists(confpath)
    assert confpath.read_text() == """GRUB_TIMEOUT=0
GRUB_CMDLINE_LINUX=""
GRUB_DISABLE_SUBMENU=true
GRUB_DISABLE_RECOVERY=true
GRUB_TIMEOUT_STYLE=countdown
GRUB_DEFAULT=saved
"""
