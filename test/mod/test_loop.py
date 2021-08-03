#
# Test for the loop.py
#

import contextlib
import os


from tempfile import TemporaryDirectory

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
        lo = ctl.loop_for_fd(f.fileno())

        assert lo
        assert lo.devname

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
