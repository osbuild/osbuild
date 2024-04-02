#!/usr/bin/python3

from unittest.mock import patch

import pytest

from osbuild.testutil import make_fake_tree, mock_command

STAGE_NAME = "org.osbuild.users"

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


@pytest.mark.parametrize("user_opts,expected_args", TEST_CASES)
def test_users_mock_bin(tmp_path, stage_module, user_opts, expected_args):
    with mock_command("chroot", "") as mocked_chroot:
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
        assert len(mocked_chroot.call_args_list) == 1
        assert mocked_chroot.call_args_list[0][2:] == expected_args + ["foo"]


# separate test right now as it results in two binaries being called
# (adduser,chage) which our parameter tests cannot do yet
def test_users_with_expire_date(tmp_path, stage_module):
    with mock_command("chroot", "") as mocked_chroot:
        make_fake_tree(tmp_path, {
            "/etc/passwd": "",
        })

        options = {
            "users": {
                "foo": {
                    "password_changed_date": "12345",
                },
            }
        }

        stage_module.main(tmp_path, options)
        assert len(mocked_chroot.call_args_list) == 2
        assert mocked_chroot.call_args_list[0][1:] == ["useradd", "foo"]
        assert mocked_chroot.call_args_list[1][1:] == ["chage", "--lastday", "12345", "foo"]
