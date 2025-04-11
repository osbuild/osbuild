#!/usr/bin/python3

import re

import pytest

from osbuild.testutil import (
    assert_jsonschema_error_contains,
)

STAGE_NAME = "org.osbuild.waagent.conf"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({}, r"'config' is a required property"),
    ({"config": {"Unsupported": True}}, r"Additional properties are not allowed \('Unsupported' was unexpected\)"),
    ({"config": {"Provisioning.UseCloudInit": 42}}, r"42 is not of type 'boolean'"),
    ({"config": {"Provisioning.Enabled": "abc"}}, r"'abc' is not of type 'boolean'"),
    ({"config": {"ResourceDisk.Format": 42}}, r"42 is not of type 'boolean'"),
    ({"config": {"ResourceDisk.EnableSwap": "abc"}}, r"'abc' is not of type 'boolean'"),
    # good
    ({"config": {}}, ""),
    ({
        "config": {
            "Provisioning.UseCloudInit": True,
            "Provisioning.Enabled": True,
            "ResourceDisk.Format": False,
            "ResourceDisk.EnableSwap": False,
        },
    }, ""),
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
        assert_jsonschema_error_contains(res, re.compile(expected_err), expected_num_errs=1)
