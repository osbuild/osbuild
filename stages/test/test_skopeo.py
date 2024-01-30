#!/usr/bin/python3

import os.path

import pytest

import osbuild.meta
from osbuild import testutil

STAGE_NAME = "org.osbuild.skopeo"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({}, "'destination' is a required property"),
    ({"destination": {}}, "is not valid under any of the given schemas"),
    ({"destination": {"type": "foo"}}, "is not valid under any of the given schemas"),
    ({"destination": {"type": "oci"}}, "is not valid under any of the given schemas"),
    # good
    ({"destination": {"type": "oci", "path": "/foo"}}, ""),

    # this one might not be expected but it's valid because we don't require any
    # *inputs* and it'll be a no-op in the stage
    ({"destination": {"type": "containers-storage"}}, ""),
])
def test_schema_validation_skopeo(test_data, expected_err):
    root = os.path.join(os.path.dirname(__file__), "../..")
    mod_info = osbuild.meta.ModuleInfo.load(root, "Stage", STAGE_NAME)
    schema = osbuild.meta.Schema(mod_info.get_schema(version="2"), STAGE_NAME)

    test_input = {
        "type": STAGE_NAME,
        "options": {},
    }
    test_input["options"].update(test_data)
    res = schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)
