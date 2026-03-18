#
# Test for the build root
#

import os
import pathlib
import sys
from tempfile import TemporaryDirectory

import pytest

import osbuild.meta
from osbuild.buildroot import BuildRoot
from osbuild.monitor import LogMonitor, NullMonitor

from ..test import TestBase


@pytest.fixture(name="tempdir")
def tempdir_fixture():
    with TemporaryDirectory(prefix="lvm2-") as tmp:
        yield tmp


@pytest.fixture(name="runner")
def runner_fixture():
    meta = osbuild.meta.Index(os.curdir)
    runner = meta.detect_host_runner()
    return runner.path


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_basic(tempdir, runner):
    libdir = os.path.abspath(os.curdir)
    var = pathlib.Path(tempdir, "var")
    var.mkdir()

    monitor = NullMonitor(sys.stderr.fileno())
    with BuildRoot("/", runner, libdir, var) as root:

        r = root.run(["/usr/bin/true"], monitor)
        assert r.returncode == 0

        # Test we can use `.run` multiple times
        r = root.run(["/usr/bin/true"], monitor)
        assert r.returncode == 0, f"{r.stdout} {r.stderr}"

        r = root.run(["/usr/bin/false"], monitor)
        assert r.returncode != 0

        # Test that fs setup looks correct
        r = root.run(["test", "-d", "/var/tmp"], monitor)
        assert r.returncode == 0
        r = root.run(["stat", "--format=%a", "/var/tmp"], monitor)
        assert r.returncode == 0
        assert "1777" in r.stdout.strip().split("\n")


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_runner_fail(tempdir):
    runner = "org.osbuild.nonexistantrunner"
    libdir = os.path.abspath(os.curdir)
    var = pathlib.Path(tempdir, "var")
    var.mkdir()

    logfile = os.path.join(tempdir, "log.txt")

    with BuildRoot("/", runner, libdir, var) as root, \
            open(logfile, "w", encoding="utf8") as log:

        monitor = LogMonitor(log.fileno())

        r = root.run(["/usr/bin/true"], monitor)

    assert r.returncode == 1
    with open(logfile, encoding="utf8") as f:
        log = f.read()
    assert log
    assert r.output
    assert log == r.output


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_output(tempdir, runner):
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
def test_bind_mounts(tempdir, runner):
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
@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_selinuxfs_ro(tempdir, runner):
    # /sys/fs/selinux must never be writable in the container
    # because RPM and other tools must not assume the policy
    # of the host is the valid policy

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
def test_proc_overrides(tempdir, runner):
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
def test_timeout(tempdir, runner):
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


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_env_isolation(tempdir, runner):
    libdir = os.path.abspath(os.curdir)
    var = pathlib.Path(tempdir, "var")
    var.mkdir()

    monitor = NullMonitor(sys.stderr.fileno())

    ipc = pathlib.Path(tempdir, "ipc")
    ipc.mkdir()

    # Set some env variable to make sure it is not leaked into
    # the container
    os.environ["OSBUILD_TEST_ENV_ISOLATION"] = "42"

    with BuildRoot("/", runner, libdir, var) as root:
        cmd = ["/bin/sh", "-c", "/usr/bin/env > /ipc/env.txt"]
        r = root.run(cmd, monitor, binds=[f"{ipc}:/ipc"])

    assert r.returncode == 0
    with open(os.path.join(ipc, "env.txt"), encoding="utf8") as f:
        data = f.read().strip()
    assert data
    have = dict(map(lambda x: x.split("=", 1), data.split("\n")))

    allowed = [
        "_",      # added by `env` itself
        "container",
        "LC_CTYPE",
        "PATH",
        "PWD",
        "PYTHONPATH",
        "PYTHONUNBUFFERED",
        "SHLVL",  # added by the shell wrapper
        "TERM",
    ]

    for k in have:
        assert k in allowed


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_caps(tempdir, runner):
    libdir = os.path.abspath(os.curdir)
    var = pathlib.Path(tempdir, "var")
    var.mkdir()

    ipc = pathlib.Path(tempdir, "ipc")
    ipc.mkdir()

    monitor = NullMonitor(sys.stderr.fileno())
    with BuildRoot("/", runner, libdir, var) as root:

        def get_caps_from_status(filename):
            with open(filename, encoding="utf8") as f:
                for line in f.readlines():
                    if line.startswith("CapEff:"):
                        return int(line[7:], base=16)  # strip "CapEff:"
                raise ValueError("CapEff not found in status file")

        def run_and_get_caps():
            cmd = ["/bin/sh", "-c", "cat /proc/self/status > /ipc/status"]
            r = root.run(cmd, monitor, binds=[f"{ipc}:/ipc"])
            assert r.returncode == 0
            return get_caps_from_status(os.path.join(ipc, "status"))

        # check case of `BuildRoot.caps` is `None`, i.e. don't drop capabilities,
        # thus the effective capabilities should be the bounding set
        assert root.caps is None

        bound_set = get_caps_from_status("/proc/self/status")
        caps = run_and_get_caps()
        assert caps == bound_set

        CAP_SYS_ADMIN = 21  # from <linux/capability.h>
        root.caps = {"CAP_SYS_ADMIN"}
        caps = run_and_get_caps()
        assert caps == (1 << CAP_SYS_ADMIN)
