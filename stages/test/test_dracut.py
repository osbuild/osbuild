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

    stage_module.main(tmp_path, options)

    assert len(mocked_run.call_args_list) == 1
    args, kwargs = mocked_run.call_args_list[0]
    assert kwargs.get("check") is True
    run_argv = args[0]
    assert run_argv[0] == "/usr/sbin/chroot"
    assert run_argv[2] == expected_argv2
