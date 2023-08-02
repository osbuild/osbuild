#
# Coherency tests for the 'osbuild.util.fscache' module.
#

# pylint: disable=protected-access

import contextlib
import errno
import os
import socket
import subprocess
import tempfile

import pytest

from osbuild.util import fscache, linux

from .. import test


def nfsd_available():
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.settimeout(1)
        return s.connect_ex(("localhost", 2049)) == 0


@contextlib.contextmanager
def mount_nfs(src: str, dst: str):
    r = subprocess.run(
        [
            "mount",
            "-t",
            "nfs",
            "-o",
            "nosharecache,vers=4",
            src,
            dst,
        ],
        check=False,
        encoding="utf-8",
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
    )
    if r.returncode != 0:
        code = r.returncode
        msg = r.stdout.strip()
        raise RuntimeError(f"{msg} (code: {code})")

    try:
        yield dst
    finally:
        subprocess.run(
            ["umount", dst],
            check=True,
        )


@pytest.fixture(name="nfsmnt")
def nfsmnt_fixture():
    tmpmnt = None
    try:
        tmpmnt = tempfile.mkdtemp(prefix="osbuild-test-", dir="/var/tmp")
        with mount_nfs("localhost:/", tmpmnt) as tmpnfs:
            with tempfile.TemporaryDirectory(dir=tmpnfs) as tmpdir:
                yield tmpdir
    finally:
        os.rmdir(tmpmnt)


@pytest.fixture(name="nfsmnts")
def nfsmnts_fixture():
    tmpmnt = None
    try:
        tmpmnt = tempfile.mkdtemp(prefix="osbuild-test-", dir="/var/tmp")
        os.mkdir(os.path.join(tmpmnt, "a"))
        os.mkdir(os.path.join(tmpmnt, "b"))
        with mount_nfs("localhost:/", os.path.join(tmpmnt, "a")), mount_nfs("localhost:/", os.path.join(tmpmnt, "b")):
            with tempfile.TemporaryDirectory(dir=os.path.join(tmpmnt, "a")) as tmpdir:
                dirname = os.path.basename(os.path.normpath(tmpdir))
                a = os.path.join(tmpmnt, "a", dirname)
                b = os.path.join(tmpmnt, "b", dirname)
                yield (a, b)
    finally:
        os.rmdir(os.path.join(tmpmnt, "b"))
        os.rmdir(os.path.join(tmpmnt, "a"))
        os.rmdir(tmpmnt)


@pytest.mark.skipif(not nfsd_available(), reason="NFSv4 daemon required")
@pytest.mark.skipif(not test.TestBase.can_bind_mount(), reason="Bind-mounting required")
def test_nfs_characteristics(nfsmnts):
    #
    # Test NFS Characteristic
    #
    # This mounts a single NFS instance with `nosharedcache` twice. It then
    # runs a series of custom tests to verify cache-behavior of NFS and how
    # different operations will cause stale caches and thus validate our
    # assumptions on how to avoid them.
    #

    a = nfsmnts[0]
    b = nfsmnts[1]

    # `stat` does not invalidate caches
    #
    # Write a fresh file on A, then stat it on B. This will properly re-fetch
    # all information since caches on both sides are empty. Then re-write the
    # file on A and, again, stat it on B and verify that the metadata was *NOT*
    # re-fetched, since NFS caches this information.
    # As last step read the file on B and verify that `open()` will properly
    # re-fetch all information.

    with open(os.path.join(a, "0_foo"), "x", encoding="utf8") as f:
        f.write("foo")

    assert os.stat(os.path.join(b, "0_foo")).st_size == 3

    with open(os.path.join(a, "0_foo"), "w", encoding="utf8") as f:
        f.write("foobar")

    assert os.stat(os.path.join(b, "0_foo")).st_size == 3

    with open(os.path.join(b, "0_foo"), "r", encoding="utf8") as f:
        assert f.read() == "foobar"

    assert os.stat(os.path.join(b, "0_foo")).st_size == 6

    # Lock-acquisition invalidates caches
    #
    # Create a file on A and commit it to disk. Open it for reading on A, but
    # then delete it on B. Verify on B it is gone. On A continue reading the
    # file. Stat it on A to verify the caches have not been invalidated. Then
    # acquire a read-lock on the open file and try the same again, this time
    # the cache should reflect the unlink.

    with open(os.path.join(a, "1_foo"), "x", encoding="utf8") as f:
        f.write("foo")

    with open(os.path.join(a, "1_foo"), "r", encoding="utf8") as f:
        os.unlink(os.path.join(b, "1_foo"))
        assert not os.access(os.path.join(b, "1_foo"), os.R_OK)

        assert f.read() == "foo"
        assert os.stat(f.fileno()).st_nlink == 1
        assert os.stat(os.path.join(a, "1_foo")).st_ino != 0
        assert os.access(os.path.join(a, "1_foo"), os.R_OK)

        linux.fcntl_flock(f.fileno(), linux.fcntl.F_RDLCK, wait=True)

        # The first STAT after an unlink returns a link-count of 0,
        # while every following STAT raises ESTALE. Lets try
        # verifying that, but do not depend on it and allow the
        # first STAT to raise ESTALE as well.
        try:
            assert os.stat(f.fileno()).st_nlink == 0
        except OSError as e:
            assert e.errno == errno.ESTALE

        with pytest.raises(OSError):
            os.stat(f.fileno())
        with pytest.raises(OSError):
            os.stat(os.path.join(a, "1_foo"))

        assert not os.access(os.path.join(a, "1_foo"), os.R_OK)

    # Inode changes on replacement
    #
    # Create a file, STAT it on A and B and verify they match and the
    # caches are active. Then replace the file on A and STAT again. The
    # replacement will be visible on A, but the caches on B still yield
    # the same old value. However, after opening on B, the file content
    # will yield the updated data and so will STAT.

    with open(os.path.join(a, "2_foo"), "x", encoding="utf8") as f:
        f.write("foo")

    st_a0 = os.stat(os.path.join(a, "2_foo"))
    st_b0 = os.stat(os.path.join(b, "2_foo"))
    assert st_a0.st_ino == st_b0.st_ino

    with open(os.path.join(a, "2_bar"), "x", encoding="utf8") as f:
        f.write("bar")
    os.rename(os.path.join(a, "2_bar"), os.path.join(a, "2_foo"))

    st_a1 = os.stat(os.path.join(a, "2_foo"))
    st_b1 = os.stat(os.path.join(b, "2_foo"))

    assert st_a1.st_ino != st_b1.st_ino
    assert st_b0.st_ino == st_b1.st_ino

    with open(os.path.join(b, "2_foo"), "r", encoding="utf8") as f:
        assert f.read() == "bar"

    st_a2 = os.stat(os.path.join(a, "2_foo"))
    st_b2 = os.stat(os.path.join(b, "2_foo"))

    assert st_a2.st_ino == st_b2.st_ino


def _test_atomics_with(a: str, b: str):
    with fscache.FsCache("osbuild-test-appid", a) as cache:
        cache.info = cache.info._replace(maximum_size=1024)

        # Test _atomic_open() with open+lock race
        #
        # Create a file `0_foo` and OPEN+LOCK it with _atomic_open(). Use a
        # tracer to hook between OPEN and LOCK. First time unlinke the target
        # file and recreate it. The second time, replace it instead.
        #
        # Verify that `_atomic_open()` needs 3 attempts to OPEN+LOCK the file,
        # and verify the content is ultimately correct.

        def _trace_lock(state: dict):
            # Use `open(..., "x")` to force an invalidation of NFS caches.
            # Otherwise, VFS would just deny our operations based on outdated
            # NFS-caches. This would be coherent, but overly restrictive.
            with pytest.raises(OSError):
                with open(os.path.join(b, "0_foo"), "x", encoding="utf8") as f:
                    pass

            if state["lock"] == 0:
                with open(os.path.join(b, "0_foo"), "r", encoding="utf8") as f:
                    assert f.read() == "foo"
                os.unlink(os.path.join(b, "0_foo"))
                with open(os.path.join(b, "0_foo"), "x", encoding="utf8") as f:
                    f.write("bar")
            elif state["lock"] == 1:
                with open(os.path.join(b, "0_foo"), "r", encoding="utf8") as f:
                    assert f.read() == "bar"
                with open(os.path.join(b, "0_foo2"), "x", encoding="utf8") as f:
                    f.write("foobar")
                os.rename(os.path.join(b, "0_foo2"), os.path.join(b, "0_foo"))

            state["lock"] = state["lock"] + 1

        state = {"lock": 0}
        cache._tracers = {"_atomic_open:lock": lambda: _trace_lock(state)}
        with open(os.path.join(a, "0_foo"), "x", encoding="utf8") as f:
            f.write("foo")
        with cache._atomic_open("0_foo", wait=True, write=False) as fd:
            with os.fdopen(fd, "r", closefd=False, encoding="utf8") as f:
                assert f.read() == "foobar"

        assert state["lock"] == 3


@pytest.mark.skipif(not test.TestBase.can_bind_mount(), reason="Bind-mounting required")
def test_atomics():
    #
    # Test FsCache Atomics (native)
    #
    # Verify the behavior of the `_atomic_*()` helpers of FsCache. Use the
    # trace-hooks of FsCache to trigger the race-conditions we want to test.
    #

    with tempfile.TemporaryDirectory(dir="/var/tmp") as tmpdir:
        _test_atomics_with(tmpdir, tmpdir)


@pytest.mark.skipif(not nfsd_available(), reason="NFSv4 daemon required")
@pytest.mark.skipif(not test.TestBase.can_bind_mount(), reason="Bind-mounting required")
def test_atomics_nfs(nfsmnts):
    #
    # Test FsCache Atomics (NFS)
    #
    # Same as `test_atomics()` but on NFS.
    #

    with tempfile.TemporaryDirectory(dir=nfsmnts[0]) as tmpdir:
        _test_atomics_with(tmpdir, tmpdir)

    # Preferably, we would now run the same tests on two distinct
    # NFS mounts with no shared caches. Unfortunately, this keeps
    # triggering kernel-oopses, so we disable the tests for now:

    # _test_atomics_with(nfsmnts[0], nfsmnts[1])
