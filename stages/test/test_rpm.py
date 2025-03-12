import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.rpm"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({"kernel_install_env": {"boot_root": "../rel"}}, "'../rel' does not match "),
    # good
    ({}, ""),
    ({"kernel_install_env": {"boot_root": "/boot"}}, ""),
])
def test_schema_validation(stage_schema, test_data, expected_err):
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
