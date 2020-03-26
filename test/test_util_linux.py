#
# Tests for the `osbuild.util.linux` module.
#


import os
import tempfile
import unittest

import osbuild.util.linux as linux


class TestUtilLinux(unittest.TestCase):
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
            try:
                linux.fcntl_flock(fd2, linux.fcntl.F_WRLCK)
                raise SystemError
            except BlockingIOError:
                pass
            linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

            # Test: write-lock1 + read-lock2 + unlock
            linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
            try:
                linux.fcntl_flock(fd2, linux.fcntl.F_RDLCK)
                raise SystemError
            except BlockingIOError:
                pass
            linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

            # Test: read-lock1 + write-lock2 + unlock
            linux.fcntl_flock(fd1, linux.fcntl.F_RDLCK)
            try:
                linux.fcntl_flock(fd2, linux.fcntl.F_WRLCK)
                raise SystemError
            except BlockingIOError:
                pass
            linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

            # Test: write-lock1 + read-lock1 + read-lock2 + unlock
            linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
            linux.fcntl_flock(fd1, linux.fcntl.F_RDLCK)
            linux.fcntl_flock(fd2, linux.fcntl.F_RDLCK)
            linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

            # Test: read-lock1 + read-lock2 + write-lock1 + unlock1 + unlock2
            linux.fcntl_flock(fd1, linux.fcntl.F_RDLCK)
            linux.fcntl_flock(fd2, linux.fcntl.F_RDLCK)
            try:
                linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
                raise SystemError
            except BlockingIOError:
                pass
            linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)
            linux.fcntl_flock(fd2, linux.fcntl.F_UNLCK)

            # Test: write-lock3 + write-lock1 + close3 + write-lock1 + unlock1
            fd3 = os.open(os.path.join("/proc/self/fd/", str(fd1)), os.O_RDWR | os.O_CLOEXEC)
            linux.fcntl_flock(fd3, linux.fcntl.F_WRLCK)
            try:
                linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
                raise SystemError
            except BlockingIOError:
                pass
            os.close(fd3)
            linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
            linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

            # Cleanup
            os.close(fd2)


if __name__ == "__main__":
    unittest.main()
