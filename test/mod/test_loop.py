#
# Test for the loop.py
#

import contextlib
import fcntl
import os
import threading
import time
from tempfile import TemporaryDirectory, TemporaryFile

import pytest

from osbuild import loop

from ..test import TestBase


@pytest.fixture(name="tempdir")
def tempdir_fixture():
    with TemporaryDirectory(prefix="loop-") as tmp:
        yield tmp


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_basic(tempdir):

    test_data = b"osbuild"

    path = os.path.join(tempdir, "test.img")
    ctl = loop.LoopControl()

    assert ctl

    with pytest.raises(ValueError):
        ctl.loop_for_fd(-1)

    lo, f = None, None
    try:
        f = open(path, "wb+")
        f.truncate(1024)
        f.flush()
        lo = ctl.loop_for_fd(f.fileno(), autoclear=True)

        assert lo.is_bound_to(f.fileno())

        sb = os.fstat(f.fileno())

        assert lo
        assert lo.devname

        info = lo.get_status()
        assert info.lo_inode == sb.st_ino
        assert info.lo_number == lo.minor

        # check for `LoopInfo.is_bound_to` helper
        assert info.is_bound_to(sb)

        with TemporaryFile(dir=tempdir) as t:
            t.write(b"")
            t.flush()

            st = os.fstat(t.fileno())
            assert not info.is_bound_to(st)

        # check for autoclear flags setting and helpers
        assert info.autoclear

        lo.set_status(autoclear=False)
        info = lo.get_status()
        assert not info.autoclear

        with open(os.path.join("/dev", lo.devname), "wb") as f:
            f.write(test_data)

        # the `flush_buf` seems to be necessary when calling
        # `LoopInfo.clear_fd`, otherwise the data integrity
        # check later will fail
        lo.flush_buf()
        lo.clear_fd()

    finally:
        if lo:
            with contextlib.suppress(OSError):
                lo.clear_fd()
            lo.close()
        if f:
            f.close()

        ctl.close()

    # check for data integrity, i.e. that what we wrote via the
    # loop device was actually written to the underlying file
    with open(path, "rb") as f:
        assert f.read(len(test_data)) == test_data

    # closing must be a no-op on a closed LoopControl
    ctl.close()

    # check we raise exceptions on methods that require
    # an open LoopControl

    for fn in (ctl.add, ctl.remove, ctl.get_unbound):
        with pytest.raises(RuntimeError):
            fn()

    with pytest.raises(RuntimeError):
        ctl.loop_for_fd(0)


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_clear_fd_wait(tempdir):

    path = os.path.join(tempdir, "test.img")
    ctl = loop.LoopControl()

    assert ctl

    delay_time = 0.25

    def close_loop(lo, barrier):
        barrier.wait()
        time.sleep(delay_time)
        print("closing loop")
        lo.close()

    lo, lo2, f = None, None, None
    try:
        f = open(path, "wb+")
        f.truncate(1024)
        f.flush()
        lo = ctl.loop_for_fd(f.fileno(), autoclear=False)
        assert lo

        # Increase reference count of the loop to > 1 thus
        # preventing the kernel from immediately closing the
        # device. Instead the kernel will set the autoclear
        # attribute and return
        lo2 = loop.Loop(lo.minor)
        assert lo2

        # as long as the second loop is alive, the kernel can
        # not clear the fd and thus we will get a timeout
        with pytest.raises(TimeoutError):
            lo.clear_fd_wait(f.fileno(), 0.1, 0.01)

        # start a thread and sync with a barrier, then close
        # the loop device in the background thread while the
        # main thread is waiting in `clear_fd_wait`. We wait
        # four times the delay time of the thread to ensure
        # we don't get a timeout.
        barrier = threading.Barrier(2)
        thread = threading.Thread(
            target=close_loop,
            args=(lo2, barrier)
        )
        barrier.reset()
        thread.start()
        barrier.wait()

        lo.clear_fd_wait(f.fileno(), 4 * delay_time, delay_time / 10)

        # no timeout exception has occurred and thus the device
        # must not be be bound to the original file anymore
        assert not lo.is_bound_to(f.fileno())

    finally:
        if lo2:
            lo2.close()
        if lo:
            with contextlib.suppress(OSError):
                lo.clear_fd()
            lo.close()
        if f:
            f.close()

        ctl.close()


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_lock(tempdir):

    path = os.path.join(tempdir, "test.img")
    ctl = loop.LoopControl()

    assert ctl

    lo, lo2, f = None, None, None
    try:
        f = open(path, "wb+")
        f.truncate(1024)
        f.flush()
        lo = ctl.loop_for_fd(f.fileno(), autoclear=True, lock=True)
        assert lo

        lo2 = loop.Loop(lo.minor)
        assert lo2

        with pytest.raises(BlockingIOError):
            lo2.flock(fcntl.LOCK_EX | fcntl.LOCK_NB)

        lo.close()
        lo = None

        # after lo is closed, the lock should be release and
        # we should be able to obtain the lock
        lo2.flock(fcntl.LOCK_EX | fcntl.LOCK_NB)
        lo2.clear_fd()

    finally:
        if lo2:
            lo2.close()
        if lo:
            lo.close()
        if f:
            f.close()

        ctl.close()


@pytest.mark.skipif(not TestBase.can_bind_mount(), reason="root only")
def test_on_close(tempdir):

    path = os.path.join(tempdir, "test.img")
    ctl = loop.LoopControl()

    assert ctl

    lo, f = None, None
    invoked = False

    def on_close(l):
        nonlocal invoked
        invoked = True

        # check that this is a no-op
        l.close()

    try:
        f = open(path, "wb+")
        f.truncate(1024)
        f.flush()
        lo = ctl.loop_for_fd(f.fileno(), autoclear=True, lock=True)
        assert lo

        lo.on_close = on_close
        lo.close()

        assert invoked

    finally:
        if lo:
            lo.close()

        ctl.close()


def test_loop_handles_error_in_init():
    with pytest.raises(FileNotFoundError):
        lopo = loop.Loop("non-existing")
