#
# Test for the build root
#

import pathlib
import os
import sys
import tempfile
import unittest

import osbuild
from osbuild.buildroot import BuildRoot
from osbuild.monitor import NullMonitor
from .. import test


@unittest.skipUnless(test.TestBase.can_bind_mount(), "root-only")
class TestBuildRoot(test.TestBase):
    """Check BuildRoot"""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_basic(self):
        # This also checks the API and BuildRoot integration:
        # the runner will call api.setup_stdio and thus check
        # that connecting to the api works correctly
        runner = "org.osbuild.linux"
        libdir = os.path.abspath(os.curdir)
        var = pathlib.Path(self.tmp.name, "var")
        var.mkdir()

        monitor = NullMonitor(sys.stderr.fileno())
        with BuildRoot("/", runner, libdir=libdir, var=var) as root:
            api = osbuild.api.API({}, monitor)
            root.register_api(api)

            r = root.run(["/usr/bin/true"])
            self.assertEqual(r.returncode, 0)

            # Test we can use `.run` multiple times
            r = root.run(["/usr/bin/true"])
            self.assertEqual(r.returncode, 0)

            r = root.run(["/usr/bin/false"])
            self.assertNotEqual(r.returncode, 0)
