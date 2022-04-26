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
from osbuild.util import linux

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


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_env_isolation(tempdir):
    runner = detect_host_runner()
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
    with open(os.path.join(ipc, "env.txt")) as f:
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
def test_caps(tempdir):
    runner = detect_host_runner()
    libdir = os.path.abspath(os.curdir)
    var = pathlib.Path(tempdir, "var")
    var.mkdir()

    ipc = pathlib.Path(tempdir, "ipc")
    ipc.mkdir()

    monitor = NullMonitor(sys.stderr.fileno())
    with BuildRoot("/", runner, libdir, var) as root:

        def run_and_get_caps():
            cmd = ["/bin/sh", "-c", "cat /proc/self/status > /ipc/status"]
            r = root.run(cmd, monitor, binds=[f"{ipc}:/ipc"])

            assert r.returncode == 0
            with open(os.path.join(ipc, "status"), encoding="utf-8") as f:
                data = f.readlines()
            assert data

            print(data)
            perm = list(filter(lambda x: x.startswith("CapEff"), data))

            assert perm and len(perm) == 1
            perm = perm[0]

            perm = perm[7:].strip()  # strip "CapEff"
            print(perm)

            caps = linux.cap_mask_to_set(int(perm, base=16))
            return caps

        # check case of `BuildRoot.caps` is `None`, i.e. don't drop capabilities,
        # thus the effective capabilities should be the bounding set
        assert root.caps is None

        bound_set = linux.cap_bound_set()

        caps = run_and_get_caps()
        assert caps == bound_set

        # drop everything but `CAP_SYS_ADMIN`
        assert "CAP_SYS_ADMIN" in bound_set

        enable = set(["CAP_SYS_ADMIN"])
        disable = bound_set - enable

        root.caps = enable

        caps = run_and_get_caps()

        for e in enable:
            assert e in caps
        for d in disable:
            assert d not in caps
