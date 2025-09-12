#!/usr/bin/python3

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.systemd-repart.create"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({"path": "image.raw"}, "'size' is a required property"),
    ({"size": "1G"}, "'path' is a required property"),
    ({"path": "image.raw", "size": "1G", "seed": 1}, "1 is not of type"),
    ({"path": 1, "size": "1G", "seed": "random"}, "1 is not of type"),
    ({"path": "image.raw", "size": 1, "seed": "random"}, "1 is not of type"),
    # good
    ({"path": "image.raw", "size": "1G"}, ""),
    ({"path": "image.raw", "size": "1G", "seed": "random"}, ""),
])
def test_systemd_repart_create_schema_validation(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": {
        }
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)
