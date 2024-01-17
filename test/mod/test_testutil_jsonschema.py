import re

import pytest

import osbuild.meta
from osbuild import testutil

fake_schema = {
    "type": "object",
    "required": ["name"],
}


@pytest.fixture(name="validation_error")
def validation_error_fixture():
    schema = osbuild.meta.Schema(fake_schema, "fake-schema")
    res = schema.validate({"not": "name"})
    assert res.valid is False
    return res


def test_assert_jsonschema_error_contains(validation_error):
    expected_err = "'name' is a required property"
    testutil.assert_jsonschema_error_contains(validation_error, expected_err)


def test_assert_jsonschema_error_regex(validation_error):
    expected_err = re.compile("'.*' is a required property")
    testutil.assert_jsonschema_error_contains(validation_error, expected_err)


def test_assert_jsonschema_error_not_contains(validation_error):
    with pytest.raises(AssertionError, match=r'not-in-errs not found in \['):
        testutil.assert_jsonschema_error_contains(validation_error, "not-in-errs")


def test_assert_jsonschema_error_not_found_re(validation_error):
    expected_err_re = re.compile("not-in-errs")
    with pytest.raises(AssertionError, match=r"re.*not found in"):
        testutil.assert_jsonschema_error_contains(validation_error, expected_err_re)


def test_assert_jsonschema_error_num_errs(validation_error):
    expected_err = "'name' is a required property"
    testutil.assert_jsonschema_error_contains(validation_error, expected_err, expected_num_errs=1)


def test_assert_jsonschema_error_num_errs_wrong(validation_error):
    expected_err = "'name' is a required property"
    with pytest.raises(AssertionError, match=r'expected exactly 99 errors in'):
        testutil.assert_jsonschema_error_contains(validation_error, expected_err, expected_num_errs=99)
