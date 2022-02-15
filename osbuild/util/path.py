"""Path handling utility functions"""
import errno
import os
import os.path
from typing import Optional

from .ctx import suppress_oserror


def clamp_mtime(path: str, start: int, to: int):
    """Clamp all modification times of 'path'

    Set the mtime of 'path' to 'to' if it is greater or equal to 'start'.
    If 'to' is None, the mtime is set to the current time.
    """

    times = (to, to)

    def fix_utime(path, dfd: Optional[int] = None):
        sb = os.stat(path, dir_fd=dfd, follow_symlinks=False)
        if sb.st_mtime < start:
            return

        # We might get a permission error when the immutable flag is set;
        # since there is nothing much we can do, we just ignore it
        with suppress_oserror(errno.EPERM):
            os.utime(path, times, dir_fd=dfd, follow_symlinks=False)

    fix_utime(path)

    for _, dirs, files, dfd in os.fwalk(path):
        for f in dirs + files:
            fix_utime(f, dfd)


def in_tree(path: str, tree: str, must_exist: bool = False) -> bool:
    """Return whether the canonical location of 'path' is under 'tree'.
    If 'must_exist' is True, the file must also exist for the check to succeed.
    """
    path = os.path.abspath(path)
    if path.startswith(tree):
        return not must_exist or os.path.exists(path)
    return False
