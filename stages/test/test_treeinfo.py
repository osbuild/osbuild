#!/usr/bin/python3
import re

import pytest

from osbuild.testutil import (
    assert_jsonschema_error_contains,
)

STAGE_NAME = "org.osbuild.treeinfo"

# https://release-engineering.github.io/productmd/treeinfo-1.0.html#examples
treeinfo_1_0_example_output = """
[checksums]
images/boot.iso=sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
images/efiboot.img=sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
images/macboot.img=sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
images/product.img=sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
images/pxeboot/initrd.img=sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
images/pxeboot/upgrade.img=sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
images/pxeboot/vmlinuz=sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
repodata/repomd.xml=sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

[general]
arch=x86_64
family=Fedora
name=Fedora 21
packagedir=Packages
platforms=x86_64,xen
repository=.
timestamp=1417653911
variant=Server
version=21

[images-x86_64]
boot.iso=images/boot.iso
initrd=images/pxeboot/initrd.img
kernel=images/pxeboot/vmlinuz
upgrade=images/pxeboot/upgrade.img

[images-xen]
initrd=images/pxeboot/initrd.img
kernel=images/pxeboot/vmlinuz
upgrade=images/pxeboot/upgrade.img

[release]
name=Fedora
short=Fedora
version=21

[stage2]
mainimage=LiveOS/squashfs.img

[tree]
arch=x86_64
build_timestamp=1417653911
platforms=x86_64,xen
variants=Server

[variant-Server]
id=Server
name=Server
packages=Packages
repository=.
type=variant
uid=Server

[header]
version=1.0
"""

treeinfo_1_0_example_input = {
    "path": "/tmp/.treeinfo",
    "treeinfo": {
        "checksums": [
            "images/boot.iso",
            "images/efiboot.img",
            "images/macboot.img",
            "images/product.img",
            "images/pxeboot/initrd.img",
            "images/pxeboot/upgrade.img",
            "images/pxeboot/vmlinuz",
            "repodata/repomd.xml"
        ],
        "general": {
            "arch": "x86_64",
            "family": "Fedora",
            "name": "Fedora 21",
            "packagedir": "Packages",
            "platforms": [
                "x86_64",
                "xen"
            ],
            "repository": ".",
            "timestamp": 1417653911,
            "variant": "Server",
            "version": "21"
        },
        "images-x86_64": {
            "boot.iso": "images/boot.iso",
            "initrd": "images/pxeboot/initrd.img",
            "kernel": "images/pxeboot/vmlinuz",
            "upgrade": "images/pxeboot/upgrade.img"
        },
        "images-xen": {
            "initrd": "images/pxeboot/initrd.img",
            "kernel": "images/pxeboot/vmlinuz",
            "upgrade": "images/pxeboot/upgrade.img"
        },
        "release": {
            "name": "Fedora",
            "short": "Fedora",
            "version": "21"
        },
        "stage2": {
            "mainimage": "LiveOS/squashfs.img"
        },
        "tree": {
            "arch": "x86_64",
            "build_timestamp": 1417653911,
            "platforms": [
                "x86_64",
                "xen"
            ],
            "variants": [
                "Server"
            ]
        },
        "variant-Server": {
            "id": "Server",
            "name": "Server",
            "packages": "Packages",
            "repository": ".",
            "type": "variant",
            "uid": "Server"
        }
    }
}


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({"path": ""}, r"'treeinfo' is a required property"),
    ({"treeinfo": {}}, r"'path' is a required property"),
    # good
    (treeinfo_1_0_example_input, ""),
])
def test_treeinfo_schema_validation(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": {},
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        assert_jsonschema_error_contains(res, re.compile(expected_err), expected_num_errs=1)


def test_treeinfo_writes_file(tmp_path, stage_module):
    treepath = tmp_path / "tree"
    confpath = "tmp/.treeinfo"
    fullpath = treepath / confpath

    # mock function make_sum to return known sha256 for empty files
    def mock_make_sum(_: str, file_path: str):
        return file_path, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    stage_module.make_sum = mock_make_sum

    stage_module.main(treepath, treeinfo_1_0_example_input)

    assert fullpath.exists()

    confdata = fullpath.read_text()

    assert "\n" + confdata == treeinfo_1_0_example_output + "\n"
