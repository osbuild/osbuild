"""Recursive File System Removal

This module implements `rm -rf` as a python function. Its core is the
`rmtree()` function, which takes a file-system path and then recursively
deletes everything it finds on that path, until eventually the path entry
itself is dropped. This is modeled around `shutil.rmtree()`.

This function tries to be as thorough as possible. That is, it tries its best
to modify permission bits and other flags to make sure directory entries can be
removed.
"""


import array
import fcntl
import os
import shutil


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

    def clear_mutable_flag(path):
        FS_IOC_GETFLAGS	= 0x80086601
        FS_IOC_SETFLAGS	= 0x40086602
        FS_IMMUTABLE_FL	= 0x010

        fd = -1
        try:
            fd = os.open(path, os.O_RDONLY)
            flags = array.array('L', [0])
            fcntl.ioctl(fd, FS_IOC_GETFLAGS, flags, True)
            flags[0] &= ~FS_IMMUTABLE_FL
            fcntl.ioctl(fd, FS_IOC_SETFLAGS, flags, False)
        except OSError:
            pass  # clearing flags is best effort
        finally:
            if fd > -1:
                os.close(fd)

    def fixperms(p):
        clear_mutable_flag(p)
        os.chmod(p, 0o777)

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
