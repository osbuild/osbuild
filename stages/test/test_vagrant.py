#!/usr/bin/python3

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.vagrant"


# Prepare dataset containing good and bad API call parameters
@pytest.mark.parametrize("test_data, expected_err", [
    # Bad API parameters
    ({}, "not valid under any of the given schemas"),
    ({"provider": "none"}, "not valid under any of the given schemas"),
    ({"provider": "virtualbox"}, "not valid under any of the given schemas"),
    ({"provider": "virtualbox", "virtualbox": {}}, "not valid under any of the given schemas"),
    ({"provider": "libvirt", "virtualbox": {"mac_address": "1"}}, "not valid under any of the given schemas"),
    # Good API parameters
    ({"provider": "libvirt"}, ""),
    ({"provider": "virtualbox", "virtualbox": {"mac_address": "000000000000"}}, ""),
])
# This test validates only API calls using correct and incorrect queries
def test_schema_validation_vagrant(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "devices": {
            "device": {
                "path": "some-path",
            },
        },
        "options": {
        }
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False, f"err: {[e.as_dict() for e in res.errors]}"
        testutil.assert_jsonschema_error_contains(res, expected_err)
