#!/usr/bin/python3

import pathlib
from unittest import mock

STAGE_NAME = "org.osbuild.systemd-sysusers"


@mock.patch("subprocess.run")
def test_systemd_sysusers(mock_run, tmp_path, stage_module):
    stage_module.main(tmp_path)

    expected = [
        "systemd-sysusers",
        "--root",
        pathlib.Path(tmp_path),
    ]
    mock_run.assert_called_with(expected, check=True)
