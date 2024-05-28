#!/usr/bin/python3

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.oscap.remediation"


@pytest.fixture(name="fake_input")
def fake_input_fixture():
    return {
        "type": STAGE_NAME,
        "options": {
            "data_dir": "/some/data/dir",
            "config": {}
        },
    }


@pytest.mark.parametrize(
    "test_data,expected_err",
    [
        ({"profile_id": "some-profile-id"}, "'datastream' is a required property"),
        ({"datastream": "some-datastream"}, "'profile_id' is a required property"),
    ],
)
def test_schema_validation_oscap_remediation(fake_input, stage_schema, test_data, expected_err):
    fake_input["options"]["config"].update(test_data)

    res = stage_schema.validate(fake_input)

    assert res.valid is False
    testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)
