#
# Tests for the `osbuild.util.linux` module.
#

import os
import subprocess
import tempfile

import pytest

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

    with open(f"{tmpdir}/immutable", "x") as f:
        assert not linux.ioctl_get_immutable(f.fileno())


@pytest.mark.skipif(not test.TestBase.can_modify_immutable("/var/tmp"), reason="root-only")
def test_ioctl_toggle_immutable(tmpdir):
    #
    # Test the `ioctl_toggle_immutable()` helper and make sure it works
    # as intended.
    #

    with open(f"{tmpdir}/immutable", "x") as f:
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
        subprocess.run(["chattr", "+i", f"{tmpdir}/immutable"], check=True)
        assert linux.ioctl_get_immutable(f.fileno())

        # Same for clearing it.
        subprocess.run(["chattr", "-i", f"{tmpdir}/immutable"], check=True)
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
