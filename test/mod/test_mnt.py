#
# Tests for mount
#
import contextlib
import os
import pathlib

import pytest

from osbuild.testutil.fs import make_fs_tree
from osbuild.util.mnt import mount_new, umount


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_mount_new(tmp_path):
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
        mount_new(src_dir, dst_dir)
        # cleanup (and test umount2 along the way)
        cm.callback(umount, dst_dir)
        # now src is bind mounted to dst and we can read the content
        assert dst_file_path.read_bytes() == b"some content"
    # ensure libc.umount2 unmounted dst again
    assert not dst_file_path.exists()
