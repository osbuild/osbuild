#
# Tests for the `osbuild.util.linux` module.
#

import contextlib
import ctypes
import os
import pathlib
import subprocess
import tempfile
import time

import pytest

from osbuild.testutil.fs import make_fs_tree
from osbuild.util import linux

from .. import test


@pytest.fixture(name="tmpdir")
def tmpdir_fixture():
    with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
        yield tmp


@pytest.mark.skipif(not test.TestBase.can_modify_immutable("/var/tmp"), reason="root-only")
def test_ioctl_get_immutable(tmpdir):
    #
    # Test the `ioctl_get_immutable()` helper and make sure it works
    # as intended.
    #

    with open(f"{tmpdir}/immutable", "x", encoding="utf8") as f:
        assert not linux.ioctl_get_immutable(f.fileno())


@pytest.mark.skipif(not test.TestBase.can_modify_immutable("/var/tmp"), reason="root-only")
def test_ioctl_toggle_immutable(tmpdir):
    #
    # Test the `ioctl_toggle_immutable()` helper and make sure it works
    # as intended.
    #

    with open(f"{tmpdir}/immutable", "x", encoding="utf8") as f:
        # Check the file is mutable by default and if we clear it again.
        assert not linux.ioctl_get_immutable(f.fileno())
        linux.ioctl_toggle_immutable(f.fileno(), False)
        assert not linux.ioctl_get_immutable(f.fileno())

        # Set immutable and check for it. Try again to verify with flag set.
        linux.ioctl_toggle_immutable(f.fileno(), True)
        assert linux.ioctl_get_immutable(f.fileno())
        linux.ioctl_toggle_immutable(f.fileno(), True)
        assert linux.ioctl_get_immutable(f.fileno())

        # Verify immutable files cannot be unlinked.
        with pytest.raises(OSError):
            os.unlink(f"{tmpdir}/immutable")

        # Check again that clearing the flag works.
        linux.ioctl_toggle_immutable(f.fileno(), False)
        assert not linux.ioctl_get_immutable(f.fileno())

        # This time, check that we actually set the same flag as `chattr`.
        subprocess.run(["chattr", "+i",
                        f"{tmpdir}/immutable"], check=True)
        assert linux.ioctl_get_immutable(f.fileno())

        # Same for clearing it.
        subprocess.run(["chattr", "-i",
                        f"{tmpdir}/immutable"], check=True)
        assert not linux.ioctl_get_immutable(f.fileno())

        # Verify we can unlink the file again, once the flag is cleared.
        os.unlink(f"{tmpdir}/immutable")


@pytest.mark.skipif(not linux.cap_is_supported(), reason="no support for capabilities")
def test_capabilities():
    #
    # Test the capability related utility functions
    #

    lib = linux.LibCap.get_default()
    assert lib
    l2 = linux.LibCap.get_default()
    assert lib is l2

    assert linux.cap_is_supported()

    assert linux.cap_is_supported("CAP_MAC_ADMIN")

    val = lib.from_name("CAP_MAC_ADMIN")
    assert val >= 0

    name = lib.to_name(val)
    assert name == "CAP_MAC_ADMIN"

    assert not linux.cap_is_supported("CAP_GICMO")
    with pytest.raises(OSError):
        lib.from_name("CAP_GICMO")


def test_fcntl_flock():
    #
    # This tests the `linux.fcntl_flock()` file-locking helper. Note
    # that file-locks are on the open-file-description, so they are shared
    # between dupped file-descriptors. We explicitly create a separate
    # file-description via `/proc/self/fd/`.
    #

    with tempfile.TemporaryFile() as f:
        fd1 = f.fileno()
        fd2 = os.open(os.path.join("/proc/self/fd/", str(fd1)), os.O_RDWR | os.O_CLOEXEC)

        # Test: unlock
        linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

        # Test: write-lock + unlock
        linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
        linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

        # Test: read-lock1 + read-lock2 + unlock1 + unlock2
        linux.fcntl_flock(fd1, linux.fcntl.F_RDLCK)
        linux.fcntl_flock(fd2, linux.fcntl.F_RDLCK)
        linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)
        linux.fcntl_flock(fd2, linux.fcntl.F_UNLCK)

        # Test: write-lock1 + write-lock2 + unlock
        linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
        with pytest.raises(BlockingIOError):
            linux.fcntl_flock(fd2, linux.fcntl.F_WRLCK)
        linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

        # Test: write-lock1 + read-lock2 + unlock
        linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
        with pytest.raises(BlockingIOError):
            linux.fcntl_flock(fd2, linux.fcntl.F_RDLCK)
        linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

        # Test: read-lock1 + write-lock2 + unlock
        linux.fcntl_flock(fd1, linux.fcntl.F_RDLCK)
        with pytest.raises(BlockingIOError):
            linux.fcntl_flock(fd2, linux.fcntl.F_WRLCK)
        linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

        # Test: write-lock1 + read-lock1 + read-lock2 + unlock
        linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
        linux.fcntl_flock(fd1, linux.fcntl.F_RDLCK)
        linux.fcntl_flock(fd2, linux.fcntl.F_RDLCK)
        linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

        # Test: read-lock1 + read-lock2 + write-lock1 + unlock1 + unlock2
        linux.fcntl_flock(fd1, linux.fcntl.F_RDLCK)
        linux.fcntl_flock(fd2, linux.fcntl.F_RDLCK)
        with pytest.raises(BlockingIOError):
            linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
        linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)
        linux.fcntl_flock(fd2, linux.fcntl.F_UNLCK)

        # Test: write-lock3 + write-lock1 + close3 + write-lock1 + unlock1
        fd3 = os.open(os.path.join("/proc/self/fd/", str(fd1)), os.O_RDWR | os.O_CLOEXEC)
        linux.fcntl_flock(fd3, linux.fcntl.F_WRLCK)
        with pytest.raises(BlockingIOError):
            linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
        os.close(fd3)
        linux.fcntl_flock(fd1, linux.fcntl.F_WRLCK)
        linux.fcntl_flock(fd1, linux.fcntl.F_UNLCK)

        # Cleanup
        os.close(fd2)


def test_libc():
    #
    # Test that the Libc class can be instantiated and provides a suitable
    # default singleton. Verify the expected interfaces exist (though tests
    # for them are separate).
    #

    libc0 = linux.Libc.make()
    libc1 = linux.Libc.default()

    assert libc0 is not libc1
    assert libc1 is linux.Libc.default()

    assert libc0.AT_FDCWD
    assert libc0.RENAME_EXCHANGE
    assert libc0.RENAME_NOREPLACE
    assert libc0.RENAME_WHITEOUT
    assert libc0.renameat2
    assert libc0.mount
    assert libc0.umount2


def test_libc_renameat2_errcheck():
    #
    # Verify the `renameat(2)` system call on `Libc` correctly turns errors into
    # python exceptions.
    #

    libc = linux.Libc.default()

    with pytest.raises(OSError):
        libc.renameat2(oldpath=b"", newpath=b"")


def test_libc_renameat2_exchange(tmpdir):
    #
    # Verify the `renameat(2)` system call on `Libc` with the
    # `RENAME_EXCHANGE` flag. This swaps two files atomically.
    #

    libc = linux.Libc.default()

    with open(f"{tmpdir}/foo", "x", encoding="utf8") as f:
        f.write("foo")
    with open(f"{tmpdir}/bar", "x", encoding="utf8") as f:
        f.write("bar")

    libc.renameat2(
        oldpath=f"{tmpdir}/foo".encode(),
        newpath=f"{tmpdir}/bar".encode(),
        flags=linux.Libc.RENAME_EXCHANGE,
    )

    with open(f"{tmpdir}/foo", "r", encoding="utf8") as f:
        assert f.read() == "bar"
    with open(f"{tmpdir}/bar", "r", encoding="utf8") as f:
        assert f.read() == "foo"


def test_proc_boot_id():
    #
    # Test the `proc_boot_id()` function which reads the current boot-id
    # from the kernel. Make sure it is a valid UUID and also consistent on
    # repeated queries.
    #

    bootid = linux.proc_boot_id("test")
    assert len(bootid.hex) == 32
    assert bootid.version == 4

    bootid2 = linux.proc_boot_id("test")
    assert bootid.int == bootid2.int

    bootid3 = linux.proc_boot_id("foobar")
    assert bootid.int != bootid3.int


def test_libc_futimens_errcheck():
    libc = linux.Libc.default()
    with pytest.raises(OSError):
        libc.futimens(-1, None)


def test_libc_futimes_works(tmpdir):
    libc = linux.Libc.default()
    stamp_file = os.path.join(tmpdir, "foo")
    with open(stamp_file, "wb") as fp:
        fp.write(b"meep")
    mtime1 = os.stat(stamp_file).st_mtime
    time.sleep(0.1)
    with open(stamp_file, "rb") as fp:
        libc.futimens(fp.fileno(), ctypes.byref(linux.c_timespec_times2(
            atime=linux.c_timespec(tv_sec=3, tv_nsec=300 * 1000 * 1000),
            mtime=linux.c_timespec(tv_sec=0, tv_nsec=libc.UTIME_OMIT),
        )))
    assert os.stat(stamp_file).st_atime == 3.3
    assert round(os.stat(stamp_file).st_mtime, 3) == round(mtime1, 3)


def test_libc_mount_errcheck():
    libc = linux.Libc.default()

    with pytest.raises(OSError, match=r"No such file or directory"):
        libc.mount(source=b"/not-exists", target=b"/target", fstype=b"", flags=0)


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_libc_mount_bind_mount(tmp_path):
    libc = linux.Libc.default()

    # create a /src and bind mount on /dst
    make_fs_tree(tmp_path, {
        "/src/src-file": "some content",
        "/dst/": None,
    })
    src_file_path = pathlib.Path(f"{tmp_path}/src/src-file")
    src_dir = os.fspath(src_file_path.parent).encode("utf-8")
    dst_file_path = pathlib.Path(f"{tmp_path}/dst/src-file")
    dst_dir = os.fspath(dst_file_path.parent).encode("utf-8")

    # fake src exists but dst not yet as it's not yet mounted
    assert src_file_path.exists()
    assert not dst_file_path.exists()
    with contextlib.ExitStack() as cm:
        libc.mount(src_dir, dst_dir, b"none", libc.MS_BIND)
        # cleanup (and test umount2 along the way)
        cm.callback(libc.umount2, dst_dir, 0)
        # now src is bind mounted to dst and we can read the content
        assert dst_file_path.read_bytes() == b"some content"
    # ensure libc.umount2 unmounted dst again
    assert not dst_file_path.exists()
