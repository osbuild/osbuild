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


@patch("subprocess.run", return_value=RunReturn())
def test_chroot_context(mocked_run):

    with Chroot("") as chroot:  # the path doesn't matter since nothing is actually running
        chroot.run(["/bin/true"])

    # We expect 7 calls to run(): 3 mount + chroot + 3 umount
    expected_cmds = ["/usr/bin/mount"] * 3 + ["/usr/sbin/chroot"] + ["/usr/bin/umount"] * 3
    assert mocked_run.call_count == len(expected_cmds)

    cmds = []
    for call in mocked_run.call_args_list:
        argv = call.args[0]
        cmds.append(argv[0])

    assert cmds == expected_cmds
