"""Scratch Directory

This module implements a scratch-directory. It allows creating temporary
directories with lock-files. It ensures the temporary directories are correctly
removed again, once they are no longer needed.
"""


import contextlib
import errno
import os
import uuid

from osbuild.util import linux, rmrf


__all__ = [
    "scratch",
]


@contextlib.contextmanager
def scratch(path_fs: str, filename_lock: str = "directory.lock", cleanup_on_success: bool = True):
    """Allocate Scratch Directory

    This creates a new scratch directory, yields control to the caller and once
    control is returned this will completely wipe the scratch directory again.

    The scratch-dir implementation makes sure to clean everything up in case of
    any exceptions raised during runtime. However, there are cases with
    asynchronous exceptions that python cannot handle. Hence, sometimes there
    might be remnants after a process crashed. However, the lockfiles created
    by all scratch-dirs allow parallel cleanup routines to check whether a
    directory is still used, and if not, it can be cleaned up.

    Parameters:
    -----------
    path_fs
        The file-system path where to create a scratch-directory under.
    filename_lock
        The file-name to use for the lock-file in the scratch directory.
    cleanup_on_success
        Whether to cleanup everything and remove the entire scratch-directory
        even when no exception was raised. This defaults to `True` and means
        nothing will remain. If set to `False`, the entry is still cleaned up
        if an exception is raised, but not if the caller signals success.
    """

    path = None
    lockfd = None
    cleanup = True

    try:
        # We create a unique new directory for the object. We do this in a
        # retry-loop to account for parallel cleanups. In the directory, we
        # create a lock-file and then acquire it. If any parallel cleanup
        # interrupts us, we simply retry.
        #
        # Note that we consider anyone taking a write-lock on the entry to be
        # responsible for it from that moment on. This usually implies only the
        # creation and destruction paths should take a write-lock. If you take
        # it for other reasons, you will own the entry from that point on.
        #
        # If a parallel cleanup uses `scandir(2)` (or `getdents(2)` for that
        # matter) to find stale entries and then tries to delete them, we retry
        # our operation. This loop will terminate, because directory scanning
        # uses generation-counters, and thus is guaranteed to terminate. A
        # parallel directory modification cannot cause it to loop indefinitely.
        # At the same time, this guarantees that we will eventually succeed in
        # creating the entry, unless you contiously spawn cleanup routines in
        # parallel to this.
        while path is None:
            # We generate a unique name for the directory. We rely on the UUID
            # generator for sufficient uniqueness. We rely on the uniqueness,
            # and we expect complying parallel actors to use a similar logic.
            name = uuid.uuid4().hex
            path = os.path.join(path_fs, name)
            path_lock = os.path.join(path, filename_lock)

            # Create directory entry. Once this succeeds, the entry is live
            # and can be discovered by parallel cleanup routines. This means,
            # we have to consider a parallel `rmdir(2)` on the directory.
            os.mkdir(path)

            # Create and open a lock-file in the directory. Preferably we used
            # `O_TMPFILE` and then moved the acquired lock-file into place. But
            # this does not work on older machines (especially `overlayfs` did
            # not support it as late as 2018). Hence, we first create the file,
            # then we acquire the lock, and then we deal with possible races.
            flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
            try:
                lockfd = os.open(path_lock, flags, 0o644)
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise

                # Someone deleted the directory entry before we could create
                # the lock-file. There is nothing for us to do but retry.
                path = None
                continue

            # Acquire a write-lock on the lock-file. This will succeed except
            # if someone acquired the write-lock before us.
            try:
                linux.fcntl_flock(lockfd, linux.fcntl.F_WRLCK)
            except BlockingIOError:
                # Someone acquired the lock before us. This means, they are
                # now responsible for it. Simply forget about the entry and
                # start over.
                lockfd = os.close(lockfd)
                path = None
                continue

            # Check that the file was still there when we got the lock. It
            # might have been all cleaned up before we got the write-lock.
            if not os.access(path_lock, os.R_OK):
                # Someone acquired the lock between us creating it and
                # acquiring it, and then deleted the lock-file. They are now
                # responsible for the remains. Forget about it and start over.
                linux.fcntl_flock(lockfd, linux.fcntl.F_UNLCK)
                lockfd = os.close(lockfd)
                path = None
                continue

        # Yield control to caller and let them use the scratch-directory.
        yield path, name

        # The caller did not signal any error. Hence, if no cleanup on success
        # was requested, we should make sure it does not happen.
        if not cleanup_on_success:
            cleanup = False
    finally:
        if lockfd is not None:
            linux.fcntl_flock(lockfd, linux.fcntl.F_UNLCK)
            lockfd = os.close(lockfd)

        if cleanup and path is not None:
            rmrf.rmtree(path)
