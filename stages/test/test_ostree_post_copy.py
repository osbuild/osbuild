#!/usr/bin/python3

from unittest.mock import call, patch

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.ostree.post-copy"


@patch("osbuild.util.ostree.cli")
def test_ostree_post_copy_smoke(mock_ostree_cli, stage_module):
    paths = {
        "mounts": "/run/osbuild/mounts",
    }
    options = {
        "sysroot": "/some/sysroot",
    }
    stage_module.main(paths, options)

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
def test_schema_validation_ostree_post_copy(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": {
            "sysroot": "/some/sysroot",
        },
    }
    test_input.update(test_data)
    res = stage_schema.validate(test_input)

    assert res.valid is False
    testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)
