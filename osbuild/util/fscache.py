"""File System Cache

This module implements a data cache that uses the file system to store data
as well as protect parallel access. It implements automatic cache management
and allows purging the cache during runtime, pruning old entries and keeping
the cache under a given limit.
"""

import contextlib
import errno
import json
import os

from osbuild.util import linux, scratchdir


__all__ = [
    "Cache",
]


@contextlib.contextmanager
def ignore_oserrors(*errnos):
    try:
        yield
    except OSError as e:
        if e.errno not in [*errnos]:
            raise


class Cache(contextlib.AbstractContextManager):
    """File System Cache

    This file system cache context represents an on-disk cache. That is, it
    allows storing information on the file system, and retrieving it from other
    contexts.

    A single cache directory can be shared between many processes at the same
    time. The cache protects access to the cached data.
    """

    class MissError(Exception):
        """Cache Miss Exception

        This error is raised under two conditions:

         1. A cache entry is requested but does not exist. There is nothing to
            provide to the caller, hence a cache-miss is raised.

         2. A cache insertion is attempted, but the cache refused the operation
            for maintenance reasons. The caller should assume the entry was
            created and immediately purged from the cache. That is, this error
            can be ignored in almost all cases.
        """

    _dirname_objects = "objects"
    _dirname_refs = "refs"
    _filename_lock = "directory.lock"
    _filename_state = "directory.state"

    _appid = None
    _path_cache = None

    _bootid = None
    _active = False

    def __init__(self, appid: str, path_cache: str):
        """Create File System Cache

        This creates a new file-system cache. It does not create the cache, nor
        access any of its content. You must enter its context-manager to prepare
        the cache for access. Any access outside of a context-manager will raise
        an assertion error.

        Parameters:
        -----------
        appid
            The application-ID of the caller. This can be any random string. It
            is used to initialize the application-specific boot-ID used to tag
            caches and detect whether an entry was created during the same boot.
        path_cache
            The path to the cache directory. The directory is created, if it
            does not exist (its parent directory must exist, though).
        """

        self._appid = appid
        self._path_cache = path_cache

    def _is_active(self):
        # Internal helper to verify we are in an active context-manager.
        return self._active

    def __enter__(self):
        assert not self._active

        # Acquire the current boot-id so we can tag entries accordingly, and
        # discard entries that are from previous boots.
        self._bootid = linux.proc_boot_id(self._appid)

        # Note: This is currently mostly a stub. In the future, we want to
        #       acquire more information on the current cache here, and then
        #       use this to perform automatic cleanups and cache maintenance
        #       whenever we enter/exit a cache context.

        self._active = True
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        # Discard any state of this context and reset to original state.
        self._active = False
        self._bootid = None
        # Note that we cannot cleanup an empty cache, since we do not know
        # whether there is another process active. We do not have a lock for
        # the entire cache, and there seems little reason to do so, as there is
        # no harm in leaving it around.

    def _create_scaffolding(self):
        # Create scaffolding directories, unless they already exist.
        dirs = [self._path_cache,
                os.path.join(self._path_cache, self._dirname_objects),
                os.path.join(self._path_cache, self._dirname_refs)]
        for i in dirs:
            try:
                os.mkdir(i)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise

    @contextlib.contextmanager
    def store(self, key: str):
        """Create new Cache Entry

        This creates a new cache entry with a unique, random name. The entry is
        created in a locked state. A reference with the given name is pointed to
        this new entry. It then yields control to the caller who can populate
        the cache entry. If the caller raises an exception, the entry and
        reference are torn down again. Otherwise, the lock is released and the
        entry is available for lookup.

        Parameters:
        -----------
        key
            The name to link a new entry as.

        Raises:
        -------
        MissError
            A cache-miss error is raised if an entry with the same reference key
            already exists, or if the cache refused to create it for maintenance
            reasons.
        """

        assert self._is_active()

        objects_path = os.path.join(self._path_cache, self._dirname_objects)
        refs_path = os.path.join(self._path_cache, self._dirname_refs)
        ref_path = os.path.join(refs_path, key)

        symlink_target = None

        # Create cache scaffolding if it does not exist, yet.
        self._create_scaffolding()

        # Create a scratch-directory, but mark it to survive in case of
        # success. This allows us to set everything up, but have it removed
        # entirely if anything goes pear shaped.
        with scratchdir.scratch(path_fs=objects_path,
                                filename_lock=self._filename_lock,
                                cleanup_on_success=False) as (path, name):
            try:
                # Create the `refs` target first. We want to make sure we own
                # that reference before creating the object. This will make
                # the reference visible early, but the write-lock makes sure
                # parallel readers will ignore the entry, and parallel writers
                # will use scratch objects instead.
                try:
                    symlink_target = os.path.join("..", self._dirname_objects, name)
                    os.symlink(symlink_target, ref_path)
                except OSError as e:
                    if e.errno == errno.EEXIST:
                        # The reference already exists. We cannot acquire a
                        # read-lock atomically on it, hence, there is no way to
                        # implement a race-free `store_or_load()` operation. But
                        # that is ok, because we simply expect the caller to try
                        # a `load()` before the `store()`. If they still hit the
                        # race condition, they should just skip the `store()`,
                        # use their temporary object and ignore the cache
                        # completely.
                        raise self.MissError()
                    raise

                # Write the state-file with information about this entry. This
                # is protected by the lock and describes metadata and state of
                # this cache entry.
                with open(os.path.join(path, self._filename_state), "x") as f:
                    state = {
                        "bootid": self._bootid.hex,
                        "refs": [key],
                    }
                    f.write(json.dumps(state))

                # Everything is set up. Yield to the caller.
                yield path
            except:
                # If the caller signalled failure, or if the setup failed for
                # spurious reasons, make sure to drop the refs-symlink, if we
                # created it. Before dropping it, make sure it points to our
                # entry. This closes a race where we are interrupted while in
                # `os.symlink()`.
                if symlink_target is not None:
                    with ignore_oserrors(errno.ENOENT):
                        c = os.readlink(ref_path)
                        if c == symlink_target:
                            os.unlink(ref_path)
                raise

    @contextlib.contextmanager
    def load(self, key: str):
        """Acquire Cache Entry

        This searches for a cache entry with the given name and then acquires a
        read-lock on it. It then yields control to the caller. Once control is
        returned, the entry is released again, regardless whether an exception
        was raised or not.

        Parameters:
        -----------
        key
            The reference name to look for.

        Raises:
        -------
        MissError
            If the entry does not exist, a cache-miss error is raised.
        """

        assert self._is_active()

        refs_path = os.path.join(self._path_cache, self._dirname_refs)
        ref_path = os.path.join(refs_path, key)

        dirfd = None
        lockfd = None

        try:
            # First try opening a path-descriptor to the entry and then a normal
            # file-descriptor for the lock-file. If either fails for `ENOENT`,
            # the entry either did not exist, or a parallel purge is ongoing.
            # In both cases, treat it as cache-miss.
            try:
                symlink_target = os.readlink(ref_path)
                path = os.path.join(refs_path, symlink_target)

                flags = os.O_PATH | os.O_CLOEXEC
                dirfd = os.open(path, flags)

                flags = os.O_RDONLY | os.O_CLOEXEC
                lockfd = os.open(self._filename_lock, flags, dir_fd=dirfd)
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise
                raise self.MissError()

            # Acquire a read-lock on the entry. If that fails, the entry is
            # still being constructed, or purged. In both cases, treat it as
            # cache miss.
            try:
                linux.fcntl_flock(lockfd, linux.fcntl.F_RDLCK)
            except BlockingIOError:
                raise self.MissError()

            # We acquired a read-lock. However, we do not know whether the lock
            # file was unlinked in between opening it and acquiring the lock. We
            # might just have acquired an anonymous lock that does not guarantee
            # anything. Hence, simply check that the lock-file is still linked
            # relative to the path-descriptor we previously opened. This path
            # descriptor pinned the actual unique cache-entry, not the reference
            # and thus is a safe anchor to check for the lock.
            if not os.access(self._filename_lock, os.R_OK, dir_fd=dirfd):
                raise self.MissError()

            # We got the entry locked. Note that the reference is not guaranteed
            # to stay alive. The only guarantee we have is that this cache entry
            # will not be purged underneath us.
            yield path
        finally:
            if lockfd is not None:
                linux.fcntl_flock(lockfd, linux.fcntl.F_UNLCK)
                lockfd = os.close(lockfd)
            if dirfd is not None:
                dirfd = os.close(dirfd)
