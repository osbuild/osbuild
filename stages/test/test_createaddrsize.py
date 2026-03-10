#!/usr/bin/python3
import os
import struct

import pytest

STAGE_NAME = "org.osbuild.createaddrsize"


def test_createaddrsize(tmp_path, stage_module):
    # make a fake initrd.img with a few bytes in it
    with open(f"{tmp_path}/initrd.img", "wb") as f:
        f.write(b"A file pretending to be an initrd.img for testing purposes")

    options = {
        "initrd": "initrd.img",
        "addrsize": "initrd.addrsize"
    }

    stage_module.main(tmp_path, options)
    assert os.path.exists(f"{tmp_path}/initrd.addrsize")
    with open(f"{tmp_path}/initrd.addrsize", "rb") as f:
        data = f.read()
    assert struct.unpack(">iiii", data) == (0, 0x2000000, 0, 58)


@pytest.mark.parametrize("test_data,expected_err", [
    # good
    (
        {
            "initrd": "/images/initrd.img",
            "addrsize": "/images/initrd.addrsize"
        },
        ""
    ),
    (
        {
            "initrd": "images/initrd.img",
            "addrsize": "images/initrd.addrsize"
        },
        ""
    ),
    # bad
    (
        {}, ["'addrsize' is a required property",
             "'initrd' is a required property"]
    ),
    (
        {
            "initrd": "/images/initrd.img",
        },
        ["'addrsize' is a required property"]
    ),
    (
        {
            "initrd": "../images/initrd.img",
            "addrsize": "images/initrd.addrsize"
        },
        ["'../images/initrd.img' does not match '^\\\\/?(?!\\\\.\\\\.)((?!\\\\/\\\\.\\\\.\\\\/).)+$'"]
    ),
])
def test_schema_validation(stage_schema, test_data, expected_err):
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
        err_msgs = sorted([e.as_dict()["message"] for e in res.errors])
        assert err_msgs == expected_err
