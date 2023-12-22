#
# Tests for the 'osbuild.util.path' module
#
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from osbuild.util import path


@pytest.fixture(name="tempdir")
def tempdir_fixture():
    with TemporaryDirectory(prefix="path-") as tmp:
        yield tmp


def test_clamp_mtime(tempdir):
    start = int(time.time())

    tree = Path(tempdir, "tree")
    tree.mkdir()
    os.makedirs(os.path.join(tree, "a", "bunch", "of", "directories"))

    file = Path(tree, "file")
    file.touch()

    folder = Path(tree, "folder")
    folder.mkdir()

    link = Path(tree, "link")
    link.symlink_to(folder, target_is_directory=True)

    timepoint = 1644758228
    path.clamp_mtime(tree, start, timepoint)

    def ensure_mtime(target, dfd):
        stat = os.stat(target, dir_fd=dfd, follow_symlinks=False)
        assert stat.st_mtime <= timepoint, f"failed for {target} ({dfd})"

    for _, dirs, files, dfd in os.fwalk(tree):
        ensure_mtime(".", dfd)

        for d in dirs:
            ensure_mtime(d, dfd)

        for f in files:
            ensure_mtime(f, dfd)


def test_in_tree():
    cases = {
        ("/tmp/file", "/tmp", False): True,  # Simple, non-existent
        ("/etc", "/", True): True,  # Simple, should exist
        ("/tmp/../../file", "/tmp", False): False,  # Relative path escape
        ("/very/fake/directory/and/file", "/very", False): True,  # non-existent, OK
        ("/very/fake/directory/and/file", "/very", True): False,  # non-existent, not-OK
        ("../..", os.path.abspath("."), False): False,  # Relative path escape from cwd
        (".", os.path.abspath("../.."), False): True,  # cwd inside parent of parent
    }

    for args, expected in cases.items():
        assert path.in_tree(*args) == expected, args
