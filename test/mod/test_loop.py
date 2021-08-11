#
# Test for the loop.py
#

import contextlib
import os
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
