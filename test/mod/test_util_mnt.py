import os
import subprocess

import pytest

from osbuild.mounts import FileSystemMountService
from osbuild.util.mnt import mount, MountGuard


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_mount_failure_msg(tmp_path):
    with pytest.raises(RuntimeError) as e:
        mount("/dev/invalid-src", tmp_path)
    assert "special device /dev/invalid-src does not exist" in str(e.value)


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_mount_guard_failure_msg(tmp_path):
    with pytest.raises(RuntimeError) as e:
        with MountGuard() as mg:
            mg.mount("/dev/invalid-src", tmp_path)
    assert "special device /dev/invalid-src does not exist" in str(e.value)


# This needs a proper refactor so that FileSystemMountService just uses
# a common mount helper.
class TestFileSystemMountService(FileSystemMountService):
    def __init__(self, args=None):
        # override __init__ to make it testable
        pass
    def translate_options(self, options):
        return options


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_osbuild_mount_failure_msg(tmp_path):
    mnt_service = TestFileSystemMountService()
    # yes, we have a third way of mounting things
    with pytest.raises(RuntimeError) as e:
        args = {
            "source": "/dev/invalid-src",
            "target": os.fspath(tmp_path),
            "root": "/",
            "options": [],
        }
        mnt_service.mount(args)
    assert "special device /dev/invalid-src does not exist" in str(e.value)

