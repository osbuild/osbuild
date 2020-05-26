#
# Tests for the `osbuild.util.osrelease` module.
#

import os
import unittest

from osbuild.util import osrelease

from .. import test


class TestUtilOSRelease(test.TestBase):
    def test_non_existant(self):
        #
        # Verify default os-release value, if no files are given.
        #

        self.assertEqual(osrelease.describe_os(), "linux")

    @unittest.skipUnless(test.TestBase.have_test_data(), "no test-data access")
    def test_describe_os(self):
        #
        # Test host os detection. test/os-release contains the os-release files
        # for all supported runners.
        #

        for entry in os.scandir(os.path.join(self.locate_test_data(), "os-release")):
            with self.subTest(entry.name):
                self.assertEqual(osrelease.describe_os(entry.path), entry.name)
