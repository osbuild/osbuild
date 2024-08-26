#
# Test for util/chroot.py
#

from unittest.mock import patch

from osbuild.util.chroot import Chroot


class RunReturn:
    """
    Class to be returned from mocked run() call so that the returncode is always 0.
    """

    @property
    def returncode(self):
        return 0


@patch("subprocess.check_call")
@patch("subprocess.run", return_value=RunReturn())
def test_chroot_context(mocked_run, mocked_check_call):

    with Chroot("") as chroot:  # the path doesn't matter since nothing is actually running
        chroot.run(["/bin/true"])

    assert mocked_run.call_count == 4  # the chroot.run() call + 3 umount calls
    assert mocked_run.call_args_list[0].args[0][0] == "/usr/sbin/chroot"
    for call_run in mocked_run.call_args_list[1:]:
        assert call_run.args[0][0] == "/usr/bin/umount"

    assert mocked_check_call.call_count == 3  # 3 mount calls
    for check_run in mocked_check_call.call_args_list:
        assert check_run.args[0][0] == "/usr/bin/mount"
