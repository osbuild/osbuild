#!/usr/bin/python3
from unittest.mock import patch

import pytest

STAGE_NAME = "org.osbuild.mks390image"


@patch("subprocess.run")
def test_mks390image(mock_run, stage_module):

    options = {
        "kernel": "/images/kernel.img",
        "initrd": "/images/initrd.img",
        "config": "/images/cdboot.prm",
        "image": "/images/cdboot.img"
    }

    stage_module.main("tree", options)
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0] == [
        "mk-s390image",
        "tree/images/kernel.img",
        "tree/images/cdboot.img",
        "-r", "tree/images/initrd.img",
        "-p", "tree/images/cdboot.prm"
    ]


@pytest.mark.parametrize("test_data,expected_err", [
    # good
    (
        {
            "kernel": "/images/kernel.img",
            "initrd": "/images/initrd.img",
            "config": "/images/cdboot.prm",
            "image": "/images/cdboot.img"
        },
        ""
    ),
    (
        {
            "kernel": "images/kernel.img",
            "initrd": "images/initrd.img",
            "config": "images/cdboot.prm",
            "image": "images/cdboot.img"
        },
        ""
    ),
    # bad
    (
        {}, ["'config' is a required property",
             "'image' is a required property",
             "'initrd' is a required property",
             "'kernel' is a required property"]
    ),
    (
        {
            "kernel": "/images/kernel.img",
            "initrd": "/images/initrd.img",
        },
        ["'config' is a required property",
         "'image' is a required property"]
    ),
    (
        {
            "kernel": "../../images/kernel.img",
            "initrd": "images/initrd.img",
            "config": "/images/cdboot.prm",
            "image": "/images/cdboot.img"
        },
        ["'../../images/kernel.img' does not match '^\\\\/?(?!\\\\.\\\\.)((?!\\\\/\\\\.\\\\.\\\\/).)+$'"]
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
