#!/usr/bin/python3

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.dnf.module-config"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({"conf": "must-be-object"}, "'must-be-object' is not of type 'object'"),
    # good
    ({
        "conf":
        {
            "name": "some-module",
            "stream": "some-stream",
            "state": "some-state",
            "profiles": ["some-profile"],
        },
    }, "")
])
def test_dnf_module_config_schema_validation(stage_schema, test_data, expected_err):
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


def test_dnf_module_config_writes_file(tmp_path, stage_module):
    treepath = tmp_path / "tree"
    confpath = "etc/dnf/modules.d/some-module.module"

    fullpath = treepath / confpath

    options = {
        "conf": {
            "name": "some-module",
            "stream": "some-stream",
            "state": "some-state",
            "profiles": ["some-profile", "other-profile"],
        }
    }

    stage_module.main(treepath, options)

    assert fullpath.exists()

    confdata = fullpath.read_text()

    assert confdata == """\
[some-module]
name = some-module
stream = some-stream
state = some-state
profiles = some-profile, other-profile

"""
