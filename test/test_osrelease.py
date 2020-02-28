import os
import unittest

import osbuild

class TestOSRelease(unittest.TestCase):
    def test_non_existant(self):
        self.assertRaises(FileNotFoundError, osbuild.pipeline.detect_os, "💩")

    def test_detect_os(self):
        """Test host os detection. test/os-release contains the os-release files
        for all supported runners.
        """
        for entry in os.scandir("test/os-release"):
            with self.subTest(entry.name):
                self.assertEqual(osbuild.pipeline.detect_os(entry.path), entry.name)

