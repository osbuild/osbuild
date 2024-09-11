#
# Test for util/chroot.py
#

import os
from unittest.mock import call, patch

from osbuild.testutil import mock_command
from osbuild.util.chroot import Chroot


class RunReturn:
    """
    Class to be returned from mocked run() call so that the returncode is always 0.
    """

    @property
    def returncode(self):
        return 0


@patch("subprocess.run", return_value=RunReturn())
def test_chroot_context(mocked_run, tmp_path):

    with Chroot(os.fspath(tmp_path)) as chroot:
        ret = chroot.run(["/bin/true"], check=True)
        assert isinstance(ret, RunReturn)
        chroot.run(["/bin/false"], check=False)

    assert mocked_run.call_args_list == [
        call(["mount", "-t", "proc", "-o", "nosuid,noexec,nodev",
              "proc", os.fspath(tmp_path / "proc")], check=True),
        call(["mount", "-t", "devtmpfs", "-o", "mode=0755,noexec,nosuid,strictatime",
              "devtmpfs", os.fspath(tmp_path / "dev")], check=True),
        call(["mount", "-t", "sysfs", "-o", "nosuid,noexec,nodev",
              "sysfs", os.fspath(tmp_path / "sys")], check=True),

        call(["chroot", os.fspath(tmp_path), "/bin/true"], check=True),
        call(["chroot", os.fspath(tmp_path), "/bin/false"], check=False),

        call(["umount", "--lazy", os.fspath(tmp_path / "proc")], check=False),
        call(["umount", "--lazy", os.fspath(tmp_path / "dev")], check=False),
        call(["umount", "--lazy", os.fspath(tmp_path / "sys")], check=False),
    ]


def test_chroot_integration(tmp_path):
    # drop the first two arguments ("chroot", "target-dir") from our fake
    # chroot
    fake_chroot = r'exec "${@:2}"'
    with mock_command("mount", ""), mock_command("umount", ""), mock_command("chroot", fake_chroot):
        with Chroot(os.fspath(tmp_path)) as chroot:
            ret = chroot.run(["/bin/true"], check=True)
            assert ret.returncode == 0
            ret = chroot.run(["/bin/false"], check=False)
            assert ret.returncode == 1
