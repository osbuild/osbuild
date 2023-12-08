import os
import subprocess
from unittest.mock import call, MagicMock, patch

import pytest

from osbuild.util.mnt import mount, MountGuard, umount


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_mount_failure_msg(tmp_path):
    with pytest.raises(RuntimeError) as e:
        mount("/dev/invalid-src", tmp_path)
    assert "special device /dev/invalid-src does not exist" in str(e.value)


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_mount_guard_failure_msg(tmp_path):
    with pytest.raises(RuntimeError) as e:
        with MountGuard() as mg:
            mg.mount("/dev/invalid-src", tmp_path)
    assert "special device /dev/invalid-src does not exist" in str(e.value)


@pytest.fixture(name="mock_completed_process")
def mock_completed_process_fixture():
    mock_completed_process = MagicMock()
    mock_completed_process.returncode = 0
    return mock_completed_process


@patch("subprocess.run")
def test_util_mnt_mount_defaults(mock_run, mock_completed_process):
    mock_run.return_value = mock_completed_process

    mount("src", "dst")
    assert len(mock_run.call_args_list) == 1
    assert mock_run.call_args == call(
        ["mount", "--rbind", "--make-rprivate", "-o", "ro,0755", "src", "dst"],
        stderr=subprocess.STDOUT, stdout=subprocess.PIPE, encoding="utf-8",
        check=False)


@patch("subprocess.run")
def test_util_mnt_umount_defaults(mock_run, mock_completed_process):
    mock_run.return_value = mock_completed_process

    umount("target")
    assert mock_run.call_args_list == [
        call(["sync", "-f", "target"], check=True),
        call(["umount", "-R", "target"], check=True),
    ]


@patch("subprocess.run")
def test_util_mnt_mount_guard_defaults(mock_run, mock_completed_process):
    mock_run.return_value = mock_completed_process

    with MountGuard() as mg:
        mg.mount("src", "dst")
    assert mock_run.call_args_list == [
        call(["mount", "--make-private", "-o", "bind,0755", "src", "dst"],
             stderr=subprocess.STDOUT, stdout=subprocess.PIPE, encoding="utf-8",
             check=False),
        call(["sync", "-f", "dst"], check=True),
        call(["umount", "dst"], check=True),
    ]
