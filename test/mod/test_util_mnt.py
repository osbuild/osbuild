import os
import re

import pytest

from osbuild.mounts import FileSystemMountService
from osbuild.util.mnt import MountGuard, mount


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_mount_failure_msg(tmp_path):
    with pytest.raises(RuntimeError) as e:
        mount("/dev/invalid-src", tmp_path)
    # latest util-linux mount uses fsconfig(2) instead of mount(2) so the
    # error is different
    assert re.search(r"special device /dev/invalid-src does not exist|Can't lookup blockdev.", str(e.value))


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_mount_guard_failure_msg(tmp_path):
    with pytest.raises(RuntimeError) as e:
        with MountGuard() as mg:
            mg.mount("/dev/invalid-src", tmp_path)
    # latest util-linux mount uses fsconfig(2) instead of mount(2) so the
    # error is different
    assert re.search(r"special device /dev/invalid-src does not exist|Can't lookup blockdev.", str(e.value))


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_mount_guard_incorrect_permissions_msg(tmp_path):
    with pytest.raises(ValueError) as e:
        with MountGuard() as mg:
            mg.mount("/dev/invalid-src", tmp_path, permissions="abc")
    assert "unknown filesystem permissions" in str(e.value)


# This needs a proper refactor so that FileSystemMountService just uses
# a common mount helper.
class FakeFileSystemMountService(FileSystemMountService):
    def __init__(self, args=None):  # pylint: disable=super-init-not-called
        # override __init__ to make it testable
        pass

    def translate_options(self, options):
        return options


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_osbuild_mount_failure_msg(tmp_path):
    mnt_service = FakeFileSystemMountService()
    # yes, we have a third way of mounting things
    with pytest.raises(RuntimeError) as e:
        args = {
            "source": "/dev/invalid-src",
            "target": os.fspath(tmp_path),
            "root": "/",
            "tree": "",
            "options": [],
        }
        mnt_service.mount(**args)
    assert re.search(
        r"special device /dev/invalid-src does not exist|Can't open blockdev.|Can't lookup blockdev", str(e.value))
