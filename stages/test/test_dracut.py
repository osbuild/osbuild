#!/usr/bin/python3

from unittest.mock import patch

import pytest

STAGE_NAME = "org.osbuild.dracut"


@pytest.mark.parametrize("with_initoverlayfs,expected_argv2", [
    (False, "/usr/bin/dracut"),
    (True, "/usr/bin/initoverlayfs-install"),
])
@patch("subprocess.run")
def test_dracut_with_initoverlayfs(mocked_run, tmp_path, stage_module, with_initoverlayfs, expected_argv2):
    options = {
        "kernel": [
            "5.14.0-247.el9.x86_64"
        ],
        "initoverlayfs": with_initoverlayfs,
    }

    stage_module.main(str(tmp_path), options)

    # We expect 7 calls to run(): 3 mount + chroot + 3 umount
    assert len(mocked_run.call_args_list) == 7
    args, kwargs = mocked_run.call_args_list[3]  # chroot is the 4th call
    assert kwargs.get("check") is True
    run_argv = args[0]
    assert run_argv[0] == "chroot"
    assert run_argv[2] == expected_argv2


@patch("subprocess.run")
def test_dracut_logger(mocked_run, tmp_path, stage_module):
    fake_logger_path = tmp_path / "usr/bin/logger"
    fake_logger_path.parent.mkdir(parents=True)
    fake_logger_path.write_text("")
    fake_true_path = tmp_path / "usr/bin/true"
    fake_true_path.write_text("")

    options = {
        "kernel": [
            "5.14.0-247.el9.x86_64",
        ]
    }
    stage_module.main(tmp_path.as_posix(), options)
    assert len(mocked_run.call_args_list) == 9
    args, kwargs = mocked_run.call_args_list[0]  # bind-mount is the 1th call
    assert kwargs.get("check") is True
    run_argv = args[0]
    assert run_argv == [
        "mount", "--rbind",
        fake_true_path.as_posix(), fake_logger_path.as_posix(),
    ]
    args, kwargs = mocked_run.call_args_list[8]  # umount is the 9th call
    assert kwargs.get("check") is False
    run_argv = args[0]
    assert run_argv == ["umount", fake_logger_path.as_posix()]
