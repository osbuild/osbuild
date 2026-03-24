import re

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.flatpak.build-import-bundle.oci"


@pytest.mark.parametrize(
    "test_data,expected_errs",
    [
        # bad
        ({}, [r"'repository' is a required property"]),
        ({"repository": "/foo"}, [r"'/foo' does not match"]),
        # good
        ({"repository": "tree:///foo"}, []),
    ],
)
def test_schema_validation_flatpak_build_import_bundle_oci(stage_schema, test_data, expected_errs):
    test_input = {
        "type": STAGE_NAME,
        "options": {},
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if not expected_errs:
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        for exp_err in expected_errs:
            testutil.assert_jsonschema_error_contains(res, re.compile(exp_err), expected_num_errs=len(expected_errs))
