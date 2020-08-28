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
from osbuild.monitor import LogMonitor, NullMonitor
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

            r = root.run(["/usr/bin/true"], monitor)
            self.assertEqual(r.returncode, 0)

            # Test we can use `.run` multiple times
            r = root.run(["/usr/bin/true"], monitor)
            self.assertEqual(r.returncode, 0)

            r = root.run(["/usr/bin/false"], monitor)
            self.assertNotEqual(r.returncode, 0)

    def test_runner_fail(self):
        runner = "org.osbuild.nonexistantrunner"
        libdir = os.path.abspath(os.curdir)
        var = pathlib.Path(self.tmp.name, "var")
        var.mkdir()

        logfile = os.path.join(self.tmp.name, "log.txt")

        with BuildRoot("/", runner, libdir=libdir, var=var) as root, \
             open(logfile, "w") as log:

            monitor = LogMonitor(log.fileno())
            api = osbuild.api.API({}, monitor)
            root.register_api(api)

            r = root.run(["/usr/bin/true"], monitor)

        self.assertEqual(r.returncode, 1)
        with open(logfile) as f:
            log = f.read()
        assert log
        assert r.output
        self.assertEqual(log, r.output)

    @unittest.skipUnless(test.TestBase.have_test_data(), "no test-data access")
    def test_bind_mounts(self):
        runner = "org.osbuild.linux"
        libdir = os.path.abspath(os.curdir)
        var = pathlib.Path(self.tmp.name, "var")
        var.mkdir()

        rw_data = pathlib.Path(self.tmp.name, "data")
        rw_data.mkdir()

        scripts = os.path.join(self.locate_test_data(), "scripts")

        monitor = NullMonitor(sys.stderr.fileno())
        with BuildRoot("/", runner, libdir=libdir, var=var) as root:
            api = osbuild.api.API({}, monitor)
            root.register_api(api)

            ro_binds = [f"{scripts}:/scripts"]

            cmd = ["/scripts/mount_flags.py",
                   "/scripts",
                   "ro"]

            r = root.run(cmd, monitor, readonly_binds=ro_binds)
            self.assertEqual(r.returncode, 0)

            cmd = ["/scripts/mount_flags.py",
                   "/rw-data",
                   "ro"]

            binds = [f"{rw_data}:/rw-data"]
            r = root.run(cmd, monitor, binds=binds, readonly_binds=ro_binds)
            self.assertEqual(r.returncode, 1)

    @unittest.skipUnless(test.TestBase.have_test_data(), "no test-data access")
    @unittest.skipUnless(os.path.exists("/sys/fs/selinux"), "no SELinux")
    def test_selinuxfs_ro(self):
        # /sys/fs/selinux must never be writable in the container
        # because RPM and other tools must not assume the policy
        # of the host is the valid policy

        runner = "org.osbuild.linux"
        libdir = os.path.abspath(os.curdir)
        var = pathlib.Path(self.tmp.name, "var")
        var.mkdir()

        scripts = os.path.join(self.locate_test_data(), "scripts")

        monitor = NullMonitor(sys.stderr.fileno())
        with BuildRoot("/", runner, libdir=libdir, var=var) as root:
            api = osbuild.api.API({}, monitor)
            root.register_api(api)

            ro_binds = [f"{scripts}:/scripts"]

            cmd = ["/scripts/mount_flags.py",
                   "/sys/fs/selinux",
                   "ro"]

            r = root.run(cmd, monitor, readonly_binds=ro_binds)
            self.assertEqual(r.returncode, 0)
