#
# Tests for the `osbuild.util.linux` module.
#

import os
import subprocess
import tempfile
import unittest

from osbuild.util import linux

from .. import test


class TestUtilLinux(unittest.TestCase):
    def setUp(self):
        self.vartmpdir = tempfile.TemporaryDirectory(dir="/var/tmp")

    def tearDown(self):
        self.vartmpdir.cleanup()

    @unittest.skipUnless(test.TestBase.can_modify_immutable("/var/tmp"), "root-only")
    def test_ioctl_get_immutable(self):
        #
        # Test the `ioctl_get_immutable()` helper and make sure it works
        # as intended.
        #

        with open(f"{self.vartmpdir.name}/immutable", "x") as f:
            assert not linux.ioctl_get_immutable(f.fileno())

    @unittest.skipUnless(test.TestBase.can_modify_immutable("/var/tmp"), "root-only")
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
