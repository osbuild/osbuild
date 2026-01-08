#!/usr/bin/python3

import pytest

from osbuild.testutil import assert_jsonschema_error_contains

STAGE_NAME = "org.osbuild.groups"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({"groups": {"!invalid-name": {}}}, "'!invalid-name' does not match any of the regex"),
    ({"groups": {"foo": {"gid": "x"}}}, "'x' is not of type 'number'"),
    # good
    ({}, ""),
    ({"groups": {"foo": {}}}, ""),
    ({"groups": {"foo": {"gid": 999}}}, ""),
    ({"groups": {"foo": {"gid": 999}}, "force": True}, ""),
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
        assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)
