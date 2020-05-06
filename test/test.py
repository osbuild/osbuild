#
# Test Infrastructure
#

import errno
import os
import subprocess
import tempfile

from osbuild.util import linux


class TestBase():
    """Base Class for Tests

    This class serves as base for our test infrastructure and provides access
    to common functionality.
    """

    @staticmethod
    def have_test_checkout() -> bool:
        """Check Test-Checkout Access

        Check whether the current test-run has access to a repository checkout
        of the project and tests. This is usually the guard around code that
        requires `locate_test_checkout()`.

        For now, we always require tests to be run from a checkout. Hence, this
        function will always return `True`. This might change in the future,
        though.
        """

        # Sanity test to verify we run from within a checkout.
        assert os.access("setup.py", os.R_OK)
        return True

    @staticmethod
    def locate_test_checkout() -> str:
        """Locate Test-Checkout Path

        This returns the path to the repository checkout we run against. This
        will fail if `have_test_checkout()` returns false.
        """

        assert TestBase.have_test_checkout()
        return os.getcwd()

    @staticmethod
    def have_test_data() -> bool:
        """Check Test-Data Access

        Check whether the current test-run has access to the test data. This
        data is required to run elaborate tests. If it is not available, those
        tests have to be skipped.

        Test data, unlike test code, is not shipped as part of the `test`
        python module, hence it needs to be located independently of the code.

        For now, we only support taking test-data from a checkout (see
        `locate_test_checkout()`). This might be extended in the future, though.
        """

        return TestBase.have_test_checkout()

    @staticmethod
    def locate_test_data() -> str:
        """Locate Test-Data Path

        This returns the path to the test-data directory. This will fail if
        `have_test_data()` returns false.
        """

        return os.path.join(TestBase.locate_test_checkout(), "test/data")

    @staticmethod
    def can_modify_immutable(path: str = "/var/tmp") -> bool:
        """Check Immutable-Flag Capability

        This checks whether the calling process is allowed to toggle the
        `FS_IMMUTABLE_FL` file flag. This is limited to `CAP_LINUX_IMMUTABLE`
        in the initial user-namespace. Therefore, only highly privileged
        processes can do this.

        There is no reliable way to check whether we can do this. The only
        possible check is to see whether we can temporarily toggle the flag
        or not. Since this is highly dependent on the file-system that file
        is on, you can optionally pass in the path where to test this. Since
        shmem/tmpfs on linux does not support this, the default is `/var/tmp`.
        """

        with tempfile.TemporaryFile(dir=path) as f:
            # First try whether `FS_IOC_GETFLAGS` is actually implemented
            # for the filesystem we test on. If it is not, lets assume we
            # cannot modify the flag and make callers skip their tests.
            try:
                b = linux.ioctl_get_immutable(f.fileno())
            except OSError as e:
                if e.errno in [errno.EACCES, errno.ENOTTY, errno.EPERM]:
                    return False
                raise

            # Verify temporary files are not marked immutable by default.
            assert not b

            # Try toggling the immutable flag. Make sure we always reset it
            # so the cleanup code can actually drop the temporary object.
            try:
                linux.ioctl_toggle_immutable(f.fileno(), True)
                linux.ioctl_toggle_immutable(f.fileno(), False)
            except OSError as e:
                if e.errno in [errno.EACCES, errno.EPERM]:
                    return False
                raise

        return True

    @staticmethod
    def have_rpm_ostree() -> bool:
        """Check rpm-ostree Availability

        This checks whether `rpm-ostree` is available in the current path and
        can be called by this process.
        """

        try:
            r = subprocess.run(["rpm-ostree", "--version"],
                               encoding="utf-8",
                               capture_output=True,
                               check=False)
        except FileNotFoundError:
            return False

        return r.returncode == 0 and "compose" in r.stdout
