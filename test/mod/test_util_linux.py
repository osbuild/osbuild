#
# Tests for the `osbuild.util.linux` module.
#

import os
import subprocess
import tempfile
import unittest

from osbuild.util import linux


def can_set_immutable():
    with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
        try:
            os.makedirs(f"{tmp}/f")
            # fist they give it ...
            subprocess.run(["chattr", "+i", f"{tmp}/f"], check=True)
            # ... then they take it away
            subprocess.run(["chattr", "-i", f"{tmp}/f"], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
        return True


class TestUtilLinux(unittest.TestCase):
    def setUp(self):
        self.vartmpdir = tempfile.TemporaryDirectory(dir="/var/tmp")

    def tearDown(self):
        self.vartmpdir.cleanup()

    def test_ioctl_get_immutable(self):
        #
        # Test the `ioctl_get_immutable()` helper and make sure it works
        # as intended.
        #

        with open(f"{self.vartmpdir.name}/immutable", "x") as f:
            assert not linux.ioctl_get_immutable(f.fileno())

    @unittest.skipUnless(can_set_immutable(), "root-only")
    def test_ioctl_toggle_immutable(self):
        #
        # Test the `ioctl_toggle_immutable()` helper and make sure it works
        # as intended.
        #

        with open(f"{self.vartmpdir.name}/immutable", "x") as f:
            # Check the file is mutable by default and if we clear it again.
            assert not linux.ioctl_get_immutable(f.fileno())
            linux.ioctl_toggle_immutable(f.fileno(), False)
            assert not linux.ioctl_get_immutable(f.fileno())

            # Set immutable and check for it. Try again to verify with flag set.
            linux.ioctl_toggle_immutable(f.fileno(), True)
            assert linux.ioctl_get_immutable(f.fileno())
            linux.ioctl_toggle_immutable(f.fileno(), True)
            assert linux.ioctl_get_immutable(f.fileno())

            # Verify immutable files cannot be unlinked.
            with self.assertRaises(OSError):
                os.unlink(f"{self.vartmpdir.name}/immutable")

            # Check again that clearing the flag works.
            linux.ioctl_toggle_immutable(f.fileno(), False)
            assert not linux.ioctl_get_immutable(f.fileno())

            # This time, check that we actually set the same flag as `chattr`.
            subprocess.run(["chattr", "+i",
                            f"{self.vartmpdir.name}/immutable"], check=True)
            assert linux.ioctl_get_immutable(f.fileno())

            # Same for clearing it.
            subprocess.run(["chattr", "-i",
                            f"{self.vartmpdir.name}/immutable"], check=True)
            assert not linux.ioctl_get_immutable(f.fileno())

            # Verify we can unlink the file again, once the flag is cleared.
            os.unlink(f"{self.vartmpdir.name}/immutable")

    def test_fcntl_flock(self):
        #
        # This tests the `linux.fcntl_flock()` file-locking helper. Note
        # that file-locks are on the open-file-description, so they are shared
        # between dupped file-descriptors. We explicitly create a separate
        # file-description via `/proc/self/fd/`.
        #

        with tempfile.TemporaryFile() as f:
            fd1 = f.fileno()
            fd2 = os.open(os.path.join("/proc/self/fd/", str(fd1)), os.O_RDWR | os.O_CLOEXEC)

            # Test: unlock
            linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

            # Test: write-lock + unlock
            linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
            linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

            # Test: read-lock1 + read-lock2 + unlock1 + unlock2
            linux.fcntl_flock(fd1, linux.fcntl.F_RDLCK)
            linux.fcntl_flock(fd2, linux.fcntl.F_RDLCK)
            linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)
            linux.fcntl_flock(fd2, linux.fcntl.F_UNLCK)

            # Test: write-lock1 + write-lock2 + unlock
            linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
            with self.assertRaises(BlockingIOError):
                linux.fcntl_flock(fd2, linux.fcntl.F_WRLCK)
            linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

            # Test: write-lock1 + read-lock2 + unlock
            linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
            with self.assertRaises(BlockingIOError):
                linux.fcntl_flock(fd2, linux.fcntl.F_RDLCK)
            linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

            # Test: read-lock1 + write-lock2 + unlock
            linux.fcntl_flock(fd1, linux.fcntl.F_RDLCK)
            with self.assertRaises(BlockingIOError):
                linux.fcntl_flock(fd2, linux.fcntl.F_WRLCK)
            linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

            # Test: write-lock1 + read-lock1 + read-lock2 + unlock
            linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
            linux.fcntl_flock(fd1, linux.fcntl.F_RDLCK)
            linux.fcntl_flock(fd2, linux.fcntl.F_RDLCK)
            linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

            # Test: read-lock1 + read-lock2 + write-lock1 + unlock1 + unlock2
            linux.fcntl_flock(fd1, linux.fcntl.F_RDLCK)
            linux.fcntl_flock(fd2, linux.fcntl.F_RDLCK)
            with self.assertRaises(BlockingIOError):
                linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
            linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)
            linux.fcntl_flock(fd2, linux.fcntl.F_UNLCK)

            # Test: write-lock3 + write-lock1 + close3 + write-lock1 + unlock1
            fd3 = os.open(os.path.join("/proc/self/fd/", str(fd1)), os.O_RDWR | os.O_CLOEXEC)
            linux.fcntl_flock(fd3, linux.fcntl.F_WRLCK)
            with self.assertRaises(BlockingIOError):
                linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
            os.close(fd3)
            linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
            linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

            # Cleanup
            os.close(fd2)
