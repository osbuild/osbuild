#
# Test for util/chroot.py
#

import os
from unittest.mock import call, patch

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
        call(["/usr/bin/mount", "-t", "proc", "-o", "nosuid,noexec,nodev",
              "proc", os.fspath(tmp_path / "proc")], check=True),
        call(["/usr/bin/mount", "-t", "devtmpfs", "-o", "mode=0755,noexec,nosuid,strictatime",
              "devtmpfs", os.fspath(tmp_path / "dev")], check=True),
        call(["/usr/bin/mount", "-t", "sysfs", "-o", "nosuid,noexec,nodev",
              "sysfs", os.fspath(tmp_path / "sys")], check=True),

        call(["/usr/sbin/chroot", os.fspath(tmp_path), "/bin/true"], check=True),
        call(["/usr/sbin/chroot", os.fspath(tmp_path), "/bin/false"], check=False),

        call(["/usr/bin/umount", "--lazy", os.fspath(tmp_path / "proc")], check=False),
        call(["/usr/bin/umount", "--lazy", os.fspath(tmp_path / "dev")], check=False),
        call(["/usr/bin/umount", "--lazy", os.fspath(tmp_path / "sys")], check=False),
    ]
