#!/usr/bin/python3
import os
from unittest.mock import patch

import pytest

from osbuild.testutil import (
    assert_jsonschema_error_contains,
    make_fake_tree,
    mock_command,
)

STAGE_NAME = "org.osbuild.users"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({"users": {"!invalid-name": {}}}, "'!invalid-name' does not match any of the regex"),
    ({"users": {"foo": {"home": 0}}}, "0 is not of type 'string'"),
    # good
    ({}, ""),
    ({"users": {"foo": {}}}, ""),
])
def test_schema_validation(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": {},
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


def test_schema_supports_bootc_style_mounts(stage_schema, bootc_devices_mounts_dict):
    test_input = bootc_devices_mounts_dict
    test_input["type"] = STAGE_NAME
    res = stage_schema.validate(test_input)
    assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"


TEST_CASES = [
    # user_opts,expected commandline args
    ({}, []),
    ({"expiredate": "12345"}, ["--expiredate", "12345"]),
]


@pytest.mark.parametrize("user_opts,expected_args", TEST_CASES)
@patch("subprocess.run")
def test_users_happy(mocked_run, tmp_path, stage_module, user_opts, expected_args):
    make_fake_tree(tmp_path, {
        "/etc/passwd": "",
    })

    args = {
        "tree": tmp_path,
    }
    options = {
        "users": {
            "foo": {},
        }
    }
    options["users"]["foo"].update(user_opts)
    stage_module.main(args, options)

    assert len(mocked_run.call_args_list) == 1
    args, kwargs = mocked_run.call_args_list[0]
    assert args[0] == ["chroot", tmp_path, "useradd"] + expected_args + ["foo"]
    assert kwargs.get("check")


@pytest.mark.parametrize("alt_root", ["", "mount:///"])
@pytest.mark.parametrize("user_opts,expected_args", TEST_CASES)
def test_users_mock_bin(tmp_path, alt_root, stage_module, user_opts, expected_args):
    with mock_command("chroot", "") as mocked_chroot:
        tree_path = tmp_path / "tree"
        fake_paths_mounts_dir = tmp_path / "run/osbuild/mounts"
        if alt_root:
            expected_work_dir = fake_paths_mounts_dir
        else:
            expected_work_dir = tree_path

        make_fake_tree(expected_work_dir, {
            "/etc/passwd": "",
        })

        args = {
            "tree": tree_path,
            "paths": {
                "mounts": fake_paths_mounts_dir,
            }
        }
        options = {
            "users": {
                "foo": {},
            }
        }
        options["users"]["foo"].update(user_opts)
        if alt_root:
            options["alt_root"] = alt_root

        stage_module.main(args, options)
        assert len(mocked_chroot.call_args_list) == 1
        # ensure we chroot into the right "tree"
        assert mocked_chroot.call_args_list[0][0] == os.fspath(expected_work_dir)
        assert mocked_chroot.call_args_list[0][2:] == expected_args + ["foo"]
