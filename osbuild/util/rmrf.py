"""Recursive File System Removal

This module implements `rm -rf` as a python function. Its core is the
`rmtree()` function, which takes a file-system path and then recursively
deletes everything it finds on that path, until eventually the path entry
itself is dropped. This is modeled around `shutil.rmtree()`.

This function tries to be as thorough as possible. That is, it tries its best
to modify permission bits and other flags to make sure directory entries can be
removed.
"""


import os
import shutil

import osbuild.util.linux as linux

__all__ = [
    "rmtree",
]


def rmtree(path: str):
    """Recursively Remove from File System

    This removes the object at the given path from the file-system. It
    recursively iterates through its content and removes them, before removing
    the object itself.

    This function is modeled around `shutil.rmtree()`, but extends its
    functionality with a more aggressive approach. It tries much harder to
    unlink file system objects. This includes immutable markers and more.

    Note that this function can still fail. In particular, missing permissions
    can always prevent this function from succeeding. However, a caller should
    never assume that they can intentionally prevent this function from
    succeeding. In other words, this function might be extended in any way in
    the future, to be more powerful and successful in removing file system
    objects.

    Parameters
    ---------
    path
        A file system path pointing to the object to remove.

    Raises
    ------
    Exception
        This raises the same exceptions as `shutil.rmtree()` (since that
        function is used internally). Consult its documentation for details.
    """

    def fixperms(p):
        fd = None
        try:

            # if we can't open the file, we just return and let the unlink
            # fail (again) with `EPERM`.
            # A notable case of why open would fail is symlinks; since we
            # want the symlink and not the target we pass the `O_NOFOLLOW`
            # flag, but this will result in `ELOOP`, thus we never change
            # symlinks. This should be fine though since "on Linux, the
            # permissions of an ordinary symbolic link are not used in any
            # operations"; see symlinks(7).
            try:
                fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
            except OSError:
                return

            # The root-only immutable flag prevents files from being unlinked
            # or modified. Clear it, so we can unlink the file-system tree.
            try:
                linux.ioctl_toggle_immutable(fd, False)
            except OSError:
                pass

            # If we do not have sufficient permissions on a directory, we
            # cannot traverse it, nor unlink its content. Make sure to set
            # sufficient permissions up front.
            try:
                os.fchmod(fd, 0o777)
            except OSError:
                pass
        finally:
            if fd is not None:
                os.close(fd)

    def unlink(p):
        try:
            os.unlink(p)
        except IsADirectoryError:
            rmtree(p)
        except FileNotFoundError:
            pass

    def on_error(_fn, p, exc_info):
        e = exc_info[0]
        if issubclass(e, FileNotFoundError):
            pass
        elif issubclass(e, PermissionError):
            if p != path:
                fixperms(os.path.dirname(p))
            fixperms(p)
            unlink(p)
        else:
            raise e

    shutil.rmtree(path, onerror=on_error)
