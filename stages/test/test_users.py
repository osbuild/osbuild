#!/usr/bin/python3

from unittest.mock import patch

import pytest

from osbuild.testutil import make_fake_tree

STAGE_NAME = "org.osbuild.users"


@pytest.mark.parametrize("user_opts,expected_args", [
    ({}, []),
    ({"expiredate": 12345}, ["--expiredate", "12345"]),
])
@patch("subprocess.run")
def test_users_happy(mocked_run, tmp_path, stage_module, user_opts, expected_args):
    make_fake_tree(tmp_path, {
        "/etc/passwd": "",
    })

    options = {
        "users": {
            "foo": {},
        }
    }
    options["users"]["foo"].update(user_opts)

    stage_module.main(tmp_path, options)

    assert len(mocked_run.call_args_list) == 1
    args, kwargs = mocked_run.call_args_list[0]
    assert args[0] == ["chroot", tmp_path, "useradd"] + expected_args + ["foo"]
    assert kwargs.get("check")
