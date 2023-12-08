import os
import subprocess

import pytest

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

