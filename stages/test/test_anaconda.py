#!/usr/bin/python3

import os.path

import pytest

import osbuild.meta


@pytest.mark.parametrize(
    "test_data,expected_err",
    [
        # BAD patterns that should not work
        ({"kickstart-modules": []}, "[] is too short"),
        ({"activatable-modules": []}, "[] is too short"),
        ({"forbidden-modules": []}, "[] is too short"),
        ({"optional-modules": []}, "[] is too short"),
        # GOOD patterns that should work, starting with a fully empty one
        ({}, ""),
        ({"kickstart-modules": ["test"]}, ""),
        ({"activatable-modules": ["test"]}, ""),
        ({"forbidden-modules": ["test"]}, ""),
        ({"optional-modules": ["test"]}, ""),
    ],
)
def test_schema_validation_smoke(test_data, expected_err):
    name = "org.osbuild.anaconda"
    root = os.path.join(os.path.dirname(__file__), "../..")
    mod_info = osbuild.meta.ModuleInfo.load(root, "Stage", name)
    schema = osbuild.meta.Schema(mod_info.get_schema(), name)

    test_input = {
        "name": name,
        "options": {},
    }
    test_input["options"].update(test_data)
    res = schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True
    else:
        # assert res.valid is False
        # assert len(res.errors) == 1
        err_msgs = [e.as_dict()["message"] for e in res.errors]
        assert expected_err in err_msgs[0]
