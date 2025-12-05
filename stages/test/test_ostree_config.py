#!/usr/bin/python3

from unittest.mock import call, patch

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.ostree.config"


@pytest.mark.parametrize("test_data,expected", [
    ({"sysroot": {"readonly": True}}, ["sysroot.readonly", "true"]),
    ({"sysroot": {"readonly": False}}, ["sysroot.readonly", "false"]),
    ({"sysroot": {"bootloader": "grub2"}}, ["sysroot.bootloader", "grub2"]),
    ({"sysroot": {"bootprefix": True}}, ["sysroot.bootprefix", "true"]),
    ({"sysroot": {"bootprefix": False}}, ["sysroot.bootprefix", "false"]),
    ({"sysroot": {"bls-append-except-default": "foobar"}}, ["sysroot.bls-append-except-default", "foobar"]),
],)
@patch("osbuild.util.ostree.cli")
def test_ostree_config(mock_ostree_cli, stage_module, test_data, expected):
    options = {
        "repo": "/ostree/repo",
        "config": {}
    }
    options["config"].update(test_data)
    stage_module.main("/run/osbuild/tree", options)
    repo = "/run/osbuild/tree/ostree/repo"
    assert mock_ostree_cli.call_args_list == [
        call("config", "set", *expected, repo=repo)]


@pytest.mark.parametrize("test_data,expected_err", [
    ({"sysroot": {"readonly": "albert"}},
     "'albert' is not of type 'boolean'"),
    ({"sysroot": {"bootloader": "lilo"}},
     "'lilo' is not one of ['none', 'auto', 'grub2', 'syslinux', 'uboot', 'zipl', 'aboot']"),
    ({"sysroot": {"bootprefix": "php"}},
     "'php' is not of type 'boolean'"),
])
def test_schema_validation_ostree_config(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": {
            "repo": "/ostree/repo",
            "config": {}
        },
    }
    test_input["options"]["config"].update(test_data)
    res = stage_schema.validate(test_input)
    assert res.valid is False
    testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)
