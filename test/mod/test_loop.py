#
# Test for the loop.py
#

import contextlib
import os
import time
import threading
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

    finally:
        if lo:
            with contextlib.suppress(OSError):
                lo.clear_fd()
            lo.close()
        if f:
            f.close()

        ctl.close()

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

        lo.clear_fd_wait(f.fileno(), 4*delay_time, delay_time/10)

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
