#
# Tests for the `osbuild.util.scratchdir` module.
#


import os
import tempfile
import unittest

from osbuild.util import scratchdir


class TestUtilScratchDir(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.dir = self.dir.cleanup()

    def test_basic(self):
        #
        # Basic Functionality Tests
        #

        # Check the initial directory is empty.
        assert len(list(os.scandir(self.dir.name))) == 0

        # Acquire a scratch-dir and check the lockfile exists.
        with scratchdir.scratch(self.dir.name, "lockname") as (path, _):
            assert os.access(os.path.join(path, "lockname"), os.R_OK)
        assert len(list(os.scandir(self.dir.name))) == 0

        # Try again, and this time try recursion.
        with scratchdir.scratch(self.dir.name, "lockname") as (path1, _):
            assert os.access(os.path.join(path1, "lockname"), os.R_OK)
            with scratchdir.scratch(self.dir.name, "lockname") as (path2, _):
                assert os.access(os.path.join(path2, "lockname"), os.R_OK)
            assert os.access(os.path.join(path1, "lockname"), os.R_OK)
        assert len(list(os.scandir(self.dir.name))) == 0
