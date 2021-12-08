#
# Test for the util.udev module
#

from tempfile import TemporaryDirectory

import pytest

from osbuild.util.udev import UdevInhibitor


@pytest.fixture(name="tempdir")
def tempdir_fixture():
    with TemporaryDirectory(prefix="udev-") as tmp:
        yield tmp


def test_udev_inhibitor(tempdir):
    ib = UdevInhibitor.for_dm_name("test", lockdir=tempdir)
    assert ib.active

    ib.release()
    assert not ib.active

    ib = UdevInhibitor.for_device(7, 1, lockdir=tempdir)
    assert ib.active

    ib.release()
    assert not ib.active

    ib.release()
    assert not ib.active
