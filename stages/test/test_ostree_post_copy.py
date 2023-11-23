#!/usr/bin/python3

import os.path
from unittest.mock import call, patch

import pytest

import osbuild.meta
from osbuild.testutil.imports import import_module_from_path


def schema_validate_stage_ostree_post_copy(test_data):
    name = "org.osbuild.ostree.post-copy"
    version = "2"
    root = os.path.join(os.path.dirname(__file__), "../..")
    mod_info = osbuild.meta.ModuleInfo.load(root, "Stage", name)
    schema = osbuild.meta.Schema(mod_info.get_schema(version=version), name)
    test_input = {
        "type": "org.osbuild.ostree.post-copy",
        "options": {
            "sysroot": "/some/sysroot",
        },
    }
    test_input.update(test_data)
    return schema.validate(test_input)


@patch("osbuild.util.ostree.cli")
def test_ostree_post_copy_smoke(mock_ostree_cli):
    stage_path = os.path.join(os.path.dirname(__file__), "../org.osbuild.ostree.post-copy")
    stage = import_module_from_path("stage", stage_path)

    paths = {
        "mounts": "/run/osbuild/mounts",
    }
    options = {
        "sysroot": "/some/sysroot",
    }
    stage.main(paths, options)

    assert mock_ostree_cli.call_args_list == [
        call("admin", "post-copy", sysroot="/run/osbuild/mounts/some/sysroot")]


@pytest.mark.parametrize(
    "test_data,expected_err",
    [
        # devices is not used directly in the stage but it's required
        # because it's used as input for "mounts", see
        # https://github.com/osbuild/osbuild/pull/1343/files#r1402161208
        ({"devices": "must-be-object"}, " is not of type 'object'"),
        ({"mounts": "must-be-array"}, " is not of type 'array'"),
    ],
)
def test_schema_validation_ostree_post_copy(test_data, expected_err):
    res = schema_validate_stage_ostree_post_copy(test_data)

    assert res.valid is False
    err_msgs = [e.as_dict()["message"] for e in res.errors]
    assert len(res.errors) == 1, err_msgs
    assert expected_err in err_msgs[0]
