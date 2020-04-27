"""Scratch Directory

This module implements a scratch-directory. It allows creating temporary
directories with lock-files. It ensures the temporary directories are correctly
removed again, once they are no longer needed.
"""


import contextlib
import errno
import os
import uuid

from osbuild.util import linux, pathfd, rmrf


__all__ = [
    "ScratchDir",
]


class ScratchDir(contextlib.AbstractContextManager):
    """Scratch Directory

    Every `ScratchDir` instance represents a temporary directory. The
    constructor takes a path to the parent directory where to create the
    temporary directory, as well as the name of the lockfile to place in the
    directory.

    By default, a scratch-dir does not perform any operations. Only once you
    enter its context-manager, it will create the directory. Once you exit it,
    all contents of the directory are removed. Re-entering the context-manager
    will create a new directory with a different name. Recursively entering the
    context-manager is supported and will retain the directory. That is, a
    scratch-dir is only cleaned up once all active context managers exited.

    The scratch-dir implementation makes sure to clean everything up in case of
    any exceptions raised during runtime. However, there are cases with
    asynchronous exceptions that python cannot handle. Hence, sometimes there
    might be remnants after a process crashed. However, the lockfiles created
    by all scratch-dirs allow parallel cleanup routines to check whether a
    directory is still used, and if not, it can be cleaned up.
    """

    _parent_dfd = None
    _lock_name = None
    _n = 0

    _name = None
    _pinned_dfd = None
    _scratch_dfd = None
    _lock_fd = None

    def __init__(self, parent_dfd: pathfd.PathFd, lock_name: str = "directory.lock"):
        self._parent_dfd = parent_dfd
        self._lock_name = lock_name
        self._n = 0

    def _first(self):
        while self._scratch_dfd is None:
            # We generate a unique name for the directory. We rely on the UUID
            # generator for sufficient uniqueness.
            self._name = uuid.uuid4().hex

            # Create our scratch directory. We pin the parent directory so it
            # cannot be closed while our context-manager is active.
            self._pinned_dfd = self._parent_dfd.clone()
            self._scratch_dfd = self._pinned_dfd.mkdir_relative(self._name)

            # Create our temporary lockfile and acquire it.
            flags = os.O_RDWR | os.O_CLOEXEC | os.O_TMPFILE
            self._lock_fd = self._pinned_dfd.open_relative(".", flags)
            linux.fcntl_flock(self._lock_fd, linux.fcntl.F_WRLCK)

            # Attempt linking the lock-file into our temporary directory. There
            # might be a parallel tempdir-cleanup running, so in case of
            # `ENOENT` we simply try again. Note that this loop will terminate,
            # if you program your cleanup correctly. Directory traversals use
            # generation counters (or similar techniques) to make sure they
            # terminate even if there are parallel additions to a directory.
            fdpath = os.path.join("/proc/self/fd/", str(self._lock_fd))
            try:
                os.link(fdpath, self._lock_name, dst_dir_fd=self._scratch_dfd.fileno())
            except OSError as e:
                if e != errno.ENOENT:
                    raise
                self._last()

    def _last(self):
        if self._lock_fd is not None:
            linux.fcntl_flock(self._lock_fd, linux.fcntl.F_UNLCK)
            self._lock_fd = os.close(self._lock_fd)

        if self._scratch_dfd is not None:
            # Call `rmrf.rmtree()` on the directory. Since it does not support
            # path-descriptors, we use the indirection via /proc.
            rmrf.rmtree(os.path.join("/proc/self/fd/",
                                     str(self._pinned_dfd.fileno()),
                                     self._name))
            self._scratch_dfd = self._scratch_dfd.close()

        if self._pinned_dfd is not None:
            self._pinned_dfd = self._pinned_dfd.close()

        self._name = None

    def __enter__(self):
        self._n += 1
        try:
            if self._n == 1:
                self._first()
        except:
            self._n -= 1
            if self._n == 0:
                self._last()
            raise
        return self._scratch_dfd

    def __exit__(self, exc_type, exc_value, exc_tb):
        self._n -= 1
        if self._n == 0:
            self._last()
