#!/usr/bin/python3

import copy
from unittest import mock

import pytest

from osbuild.testutil import make_fake_input_tree

STAGE_NAME = "org.osbuild.xorrisofs"


@mock.patch("subprocess.run")
def test_xorrisofs_mutual_exclusive_efi_efi_image(mock_run, tmp_path, stage_module):
    fake_input_tree = make_fake_input_tree(tmp_path, {
        "/some-dir/some-file.txt": "content",
    })

    inputs = {
        "efi-image": {
            "path": fake_input_tree,
            "data": {
                "files": {
                    "efiboot.img": "",
                },
            },
        },
        "tree": {
            "path": fake_input_tree,
        }
    }

    # default (syslinux)
    with pytest.raises(RuntimeError):
        stage_module.main(
            copy.deepcopy(inputs),
            tmp_path,
            {
                "filename": "test.iso",
                "volid": "test",
                "efi": "path/to",
            },
        )

    # grub2
    with pytest.raises(RuntimeError):
        stage_module.main(
            copy.deepcopy(inputs),
            tmp_path,
            {
                "grub2mbr": True,
                "filename": "test.iso",
                "volid": "test",
                "efi": "path/to",
            },
        )

    assert not mock_run.called
