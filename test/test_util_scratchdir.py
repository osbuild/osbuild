#
# Tests for the `osbuild.util.scratchdir` module.
#


import os
import tempfile
import unittest

from osbuild.util import pathfd, scratchdir


class TestUtilScratchDir(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.dirfd = pathfd.PathFd.from_path(self.dir.name)

    def tearDown(self):
        self.dirfd.close()
        self.dir.cleanup()

    def test_basic(self):
        #
        # Basic Functionality Tests
        #

        # make sure the constructor does not actually do anything
        s = scratchdir.ScratchDir(self.dirfd, "lockname")
        assert len(list(self.dirfd.enumerate())) == 0

        # acquire the scratch-dir and check the lockfile exists
        with s as fd:
            assert os.access("lockname", os.R_OK, dir_fd=fd.fileno())
        assert len(list(self.dirfd.enumerate())) == 0

        # try again, and this time try recursion
        with s as fd:
            assert os.access("lockname", os.R_OK, dir_fd=fd.fileno())
            with s as fd2:
                assert os.access("lockname", os.R_OK, dir_fd=fd2.fileno())
            assert os.access("lockname", os.R_OK, dir_fd=fd.fileno())
        assert len(list(self.dirfd.enumerate())) == 0
