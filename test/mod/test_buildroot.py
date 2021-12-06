#
# Test for the build root
#

import pathlib
import os
import sys

from tempfile import TemporaryDirectory

import pytest

from osbuild.buildroot import BuildRoot
from osbuild.monitor import LogMonitor, NullMonitor
from osbuild.pipeline import detect_host_runner

from ..test import TestBase


@pytest.fixture(name="tempdir")
def tempdir_fixture():
    with TemporaryDirectory(prefix="lvm2-") as tmp:
        yield tmp


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_basic(tempdir):
    runner = detect_host_runner()
    libdir = os.path.abspath(os.curdir)
    var = pathlib.Path(tempdir, "var")
    var.mkdir()

    monitor = NullMonitor(sys.stderr.fileno())
    with BuildRoot("/", runner, libdir, var) as root:

        r = root.run(["/usr/bin/true"], monitor)
        assert r.returncode == 0

        # Test we can use `.run` multiple times
        r = root.run(["/usr/bin/true"], monitor)
        assert r.returncode == 0

        r = root.run(["/usr/bin/false"], monitor)
        assert r.returncode != 0


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_runner_fail(tempdir):
    runner = "org.osbuild.nonexistantrunner"
    libdir = os.path.abspath(os.curdir)
    var = pathlib.Path(tempdir, "var")
    var.mkdir()

    logfile = os.path.join(tempdir, "log.txt")

    with BuildRoot("/", runner, libdir, var) as root, \
            open(logfile, "w") as log:

        monitor = LogMonitor(log.fileno())

        r = root.run(["/usr/bin/true"], monitor)

    assert r.returncode == 1
    with open(logfile) as f:
        log = f.read()
    assert log
    assert r.output
    assert log == r.output


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_output(tempdir):
    runner = detect_host_runner()
    libdir = os.path.abspath(os.curdir)
    var = pathlib.Path(tempdir, "var")
    var.mkdir()

    data = "42. cats are superior to dogs"

    monitor = NullMonitor(sys.stderr.fileno())
    with BuildRoot("/", runner, libdir, var) as root:

        r = root.run(["/usr/bin/echo", data], monitor)
        assert r.returncode == 0

    assert data in r.output.strip()


@pytest.mark.skipif(not TestBase.have_test_data(), reason="no test-data access")
@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_bind_mounts(tempdir):
    runner = detect_host_runner()
    libdir = os.path.abspath(os.curdir)
    var = pathlib.Path(tempdir, "var")
    var.mkdir()

    rw_data = pathlib.Path(tempdir, "data")
    rw_data.mkdir()

    scripts = os.path.join(TestBase.locate_test_data(), "scripts")

    monitor = NullMonitor(sys.stderr.fileno())
    with BuildRoot("/", runner, libdir, var) as root:

        ro_binds = [f"{scripts}:/scripts"]

        cmd = ["/scripts/mount_flags.py",
               "/scripts",
               "ro"]

        r = root.run(cmd, monitor, readonly_binds=ro_binds)
        assert r.returncode == 0

        cmd = ["/scripts/mount_flags.py",
               "/rw-data",
               "ro"]

        binds = [f"{rw_data}:/rw-data"]
        r = root.run(cmd, monitor, binds=binds, readonly_binds=ro_binds)
        assert r.returncode == 1


@pytest.mark.skipif(not TestBase.have_test_data(), reason="no test-data access")
@pytest.mark.skipif(not os.path.exists("/sys/fs/selinux"), reason="no SELinux")
def test_selinuxfs_ro(tempdir):
    # /sys/fs/selinux must never be writable in the container
    # because RPM and other tools must not assume the policy
    # of the host is the valid policy

    runner = detect_host_runner()
    libdir = os.path.abspath(os.curdir)
    var = pathlib.Path(tempdir, "var")
    var.mkdir()

    scripts = os.path.join(TestBase.locate_test_data(), "scripts")

    monitor = NullMonitor(sys.stderr.fileno())
    with BuildRoot("/", runner, libdir, var) as root:

        ro_binds = [f"{scripts}:/scripts"]

        cmd = ["/scripts/mount_flags.py",
               "/sys/fs/selinux",
               "ro"]

        r = root.run(cmd, monitor, readonly_binds=ro_binds)
        assert r.returncode == 0


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_proc_overrides(tempdir):
    runner = detect_host_runner()
    libdir = os.path.abspath(os.curdir)
    var = pathlib.Path(tempdir, "var")
    var.mkdir()

    cmdline = "is-this-the-real-world"

    monitor = NullMonitor(sys.stderr.fileno())
    with BuildRoot("/", runner, libdir, var) as root:

        root.proc.cmdline = cmdline

        r = root.run(["cat", "/proc/cmdline"], monitor)
        assert r.returncode == 0
        assert cmdline in r.output.strip()


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_timeout(tempdir):
    runner = detect_host_runner()
    libdir = os.path.abspath(os.curdir)
    var = pathlib.Path(tempdir, "var")
    var.mkdir()

    monitor = NullMonitor(sys.stderr.fileno())

    with BuildRoot("/", runner, libdir, var) as root:

        root.run(["/bin/sleep", "1"], monitor, timeout=2)

        with pytest.raises(TimeoutError):
            root.run(["/bin/sleep", "1"], monitor, timeout=0.1)

        with pytest.raises(TimeoutError):
            root.run(["/bin/sleep", "1"], monitor, timeout=0.1)
