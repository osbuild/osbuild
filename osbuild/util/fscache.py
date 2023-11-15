"""File System Cache

This module implements a data cache that uses the file system to store data
as well as protect parallel access. It implements automatic cache management
and allows purging the cache during runtime, pruning old entries and keeping
the cache under a given limit.
"""

# pylint: disable=too-many-lines

import contextlib
import errno
import json
import os
import subprocess
import uuid
from typing import Any, Dict, NamedTuple, Optional, Tuple, Union

from osbuild.util import ctx, linux, rmrf

__all__ = [
    "FsCache",
    "FsCacheInfo",
]


MaximumSizeType = Optional[Union[int, str]]


class FsCacheInfo(NamedTuple):
    """File System Cache Information

    This type represents static cache information. It is an immutable named
    tuple and used to query or set the configuration of a cache.

    creation_boot_id - Hashed linux boot-id at the time of cache-creation
    maximum_size - Maximum cache size in bytes, or "unlimited"
    version - version of the cache data structures
    """

    creation_boot_id: Optional[str] = None
    maximum_size: MaximumSizeType = None
    version: Optional[int] = None

    @classmethod
    def from_json(cls, data: Any) -> "FsCacheInfo":
        """Create tuple from parsed JSON

        This takes a parsed JSON value and converts it into a tuple with the
        same information. Unknown fields in the input are ignored. The input
        is usually taken from `json.load()` and similar.
        """

        if not isinstance(data, dict):
            return cls()

        creation_boot_id = None
        maximum_size: MaximumSizeType = None
        version = None

        # parse "creation-boot-id"
        _creation_boot_id = data.get("creation-boot-id")
        if isinstance(_creation_boot_id, str) and len(_creation_boot_id) == 32:
            creation_boot_id = _creation_boot_id

        # parse "maximum-size"
        _maximum_size = data.get("maximum-size")
        if isinstance(_maximum_size, int):
            maximum_size = _maximum_size
        elif isinstance(_maximum_size, str) and _maximum_size == "unlimited":
            maximum_size = "unlimited"

        # parse "version"
        _version = data.get("version")
        if isinstance(_version, int):
            version = _version

        # create immutable tuple
        return cls(
            creation_boot_id,
            maximum_size,
            version,
        )

    def to_json(self) -> Dict[str, Any]:
        """Convert tuple into parsed JSON

        Return a parsed JSON value that represents the same values as this
        tuple does. Unset values are skipped. The returned value can be
        converted into formatted JSON via `json.dump()` and similar.
        """

        data: Dict[str, Any] = {}
        if self.creation_boot_id is not None:
            data["creation-boot-id"] = self.creation_boot_id
        if self.maximum_size is not None:
            data["maximum-size"] = self.maximum_size
        if self.version is not None:
            data["version"] = self.version
        return data


class FsCache(contextlib.AbstractContextManager, os.PathLike):
    """File System Cache

    This file system cache context represents an on-disk cache. That is, it
    allows storing information on the file system, and retrieving it from other
    contexts.

    A single cache directory can be shared between many processes at the same
    time. The cache protects access to the cached data. The cache must not be
    shared over non-coherent network storage, but is designed for system-local
    linux file-systems.

    The file-system layout is as follows:

        [cache]/
        ├── cache.info
        ├── cache.lock
        ├── cache.size
        ├── objects/
        │   ├── [id0]
        │   ├── [id1]/
        │   │   ├── data/
        │   │   │   └── ...
        │   │   ├── object.info
        │   │   └── object.lock
        │   └── ...
        └── stage/
            ├── uuid-[uuid0]
            ├── uuid-[uuid1]/
            │   ├── data/
            │   │   └── ...
            │   ├── object.info
            │   └── object.lock
            └── ...

    The central data store is in the `objects` subdirectory. Every cache entry
    has a separate subdirectory there. To guard access, a read-lock on
    `object.lock` is required for all readers, a write-lock is required for all
    writers. Static information about the object is available in the
    `object.info` file.

    As an optimization, entries in the object store consisting of a single
    file can be stored directly underneath `objects` without a separate
    subdirectory hierarchy. Their guarding lock is directly taken on this file
    and no metadata is available, other than the file information itself. This
    is used extensively by the cache management to prepare objects for atomic
    replacements. Due to lack of metadata, they are volatile and can be
    deleted as soon as they are unlocked.

    Generally, access to the cache is non-blocking. That is, if a read-lock
    cannot be acquired, an entry is considered non-existant. Thus, unless
    treated as a `write-once` cache, cache efficiency will decrease when taking
    write-locks.

    The `data/` directory contains the content of a cache entry. Its content
    is solely defined by the creator of the entry and the cache makes no
    assumptions about its layout. Note that the `data/` directory itself can be
    modified (e.g., permission-changes) if an unnamed top-level directory is
    desired (e.g., to store a directory tree).

    Additionally to the `objects/` directory, a similar `stage/` directory is
    provided. This directory is `write-only` and used to prepare entries for
    the object store before committing them. The staging area is optional. It
    is completely safe to do the same directly in the object store. However,
    the separation allows putting the staging area on a different file-system
    (e.g., symlinking to a tmpfs), and thus improving performance for larger
    operations. Otherwise, the staging area follows the same rules as the
    object store, except that only writers are expected. Hence, staging entries
    always use a unique UUID as name. To commit a staging entry, a user is
    expected to create an entry in the object store and copy/move the `data/`
    directory over.

    To guard against parallel accesses, a set of locks is utilized. Generally,
    a `*.lock`-file locks the directory it is in, while a lock on any other
    file just locks that file (unfortunately, we cannot acquire write-locks on
    directories directly, since it would require opening them for writing,
    which is not possible on linux). `cache.lock` can be used to guard the
    entire cache. A write-lock will keep any other parallel operation out,
    while a read-lock merely acquires cache access (you are still allowed to
    modify the cache, but need fine-grained locking). Hence, a write-lock on the
    global `cache.lock` file is only required for operations that cannot use
    fine-grained locking. The latter requires individual locking for each file
    or each object store entry you modify. In all those cases you must ensure
    for parallel modifications, since lock acquisition on file-systems can only
    be done after opening a file.
    """

    class MissError(Exception):
        """Cache Miss Exception

        This error is raised when a cache entry is not found. Due to the
        shared nature of the cache, a caller must be aware that any entry can
        be created or deleted by other concurrent operations, at any point in
        time. Hence, a cache miss only reflects the state of the cache at a
        particular time under a particular lock.
        """

    # static parameters
    _dirname_data = "data"
    _dirname_objects = "objects"
    _dirname_stage = "stage"
    _filename_cache_info = "cache.info"
    _filename_cache_lock = "cache.lock"
    _filename_cache_size = "cache.size"
    _filename_cache_tag = "CACHEDIR.TAG"
    _filename_object_info = "object.info"
    _filename_object_lock = "object.lock"
    _version_current = 1
    _version_minimum = 1

    # constant properties
    _appid: str
    _tracers: Dict[str, Any]
    _path_cache: Any

    # context-manager properties
    _active: bool
    _bootid: Optional[str]
    _lock: Optional[int]
    _info: FsCacheInfo
    _info_maximum_size: int

    def __init__(self, appid: str, path_cache: Any):
        """Create File System Cache

        This creates a new file-system cache. It does not create the cache, nor
        access any of its content. You must enter its context-manager to prepare
        the cache for access. Any access outside of a context-manager will raise
        an assertion error, unless explicitly stated otherwise.

        Parameters:
        -----------
        appid
            The application-ID of the caller. This can be any random string. It
            is used to initialize the application-specific boot-ID used to tag
            caches and detect whether an entry was created during the same boot.
        path_cache
            The path to the cache directory. The directory (and the path to it)
            is created if it does not exist.
        """

        self._appid = appid
        self._tracers = {}
        self._path_cache = os.fspath(path_cache)

        self._active = False
        self._bootid = None
        self._lock = None
        self._info = FsCacheInfo()
        self._info_maximum_size = 0

    def _trace(self, trace: str):
        """Trace execution

        Execute registered trace-hooks for the given trace string. This allows
        tests to register callbacks that are executed at runtime at a specific
        location in the code. During normal operation, no such hooks should be
        used.

        The trace-hooks are used to trigger race-conditions during tests and
        verify they are handled gracefully.

        Parameters:
        -----------
        trace
            The trace-hook to run.
        """

        if trace in self._tracers:
            self._tracers[trace]()

    @staticmethod
    def _calculate_size(path_target: str) -> int:
        """Calculate total size of a directory tree

        Calculate the total amount of storage required for a directory tree in
        bytes. This does not account for metadata, but only for stored file
        content.

        Parameters:
        -----------
        path_target
            File-system path to the directory to operate on.
        """

        return sum(
            os.lstat(
                os.path.join(path, f)
            ).st_blocks * 512 for path, dirs, files in os.walk(
                path_target
            ) for f in files
        )

    def __fspath__(self) -> Any:
        """Return cache path

        Return the path to this cache as provided to the constructor of the
        cache. No conversions are applied, so the path is absolute if the
        path as provided by the caller was absolute, and vice-versa.

        This is part of the `os.PathLike` interface. See its documentation.
        """

        return self._path_cache

    def _path(self, *rpaths):
        """Return absolute path into cache location

        Take the relative path from the caller and turn it into an absolute
        path. Since most operations take a relative path from the cache root
        to a cache location, this function can be used to make those paths
        absolute.

        Parameters:
        -----------
        rpaths
            Relative paths from cache root to the desired cache location.
        """

        return os.path.join(self, *rpaths)

    @contextlib.contextmanager
    def _atomic_open(
        self,
        rpath: str,
        *,
        wait: bool,
        write: bool,
        closefd: bool = True,
        oflags: int = 0,
    ):
        """Atomically open and lock file

        Open the cache-file at the specified relative path and acquire a
        lock on it. Yield the file-descriptor to the caller. Once control
        returns, all locks are released (if not already done so by the
        caller) and the file-descriptor is closed.

        Note that this operation involves a retry-loop in case the file is
        replaced or moved before the lock is acquired.

        Parameters:
        -----------
        rpath
            Relative path from the cache-root to the file to open.
        wait
            Whether to wait for locks to be acquired.
        write
            If false, the file is opened for reading and a read lock is
            acquired. If true, it is opened for read and write and a write
            lock is acquired.
        closefd
            If false, retain file-descriptor (and lock) on success.
        oflags
            Additional open-flags to pass to `os.open()`.
        """

        fd = None
        path = self._path(rpath)

        try:
            while True:
                # Open the file and acquire a lock. Make sure not to modify the
                # file in any way, ever. If non-blocking operation was requested
                # the lock call will raise `EAGAIN` if contended.
                flags = os.O_RDONLY | os.O_CLOEXEC | oflags
                lock = linux.fcntl.F_RDLCK
                if write:
                    flags = flags | os.O_RDWR
                    lock = linux.fcntl.F_WRLCK
                self._trace("_atomic_open:open")
                fd = os.open(path, flags, 0o644)
                self._trace("_atomic_open:lock")
                linux.fcntl_flock(fd, lock, wait=wait)

                # The file might have been replaced between opening it and
                # acquiring the lock. Hence, run `stat(2)` on the path again
                # and compare it to `fstat(2)` of the open file. If they differ
                # simply retry.
                # On NFS, the lock-acquisition has invalidated the caches, hence
                # the metadata is refetched. On linux, the first query will
                # succeed and reflect the drop in link-count. Every further
                # query will yield `ESTALE`. Yet, we cannot rely on being the
                # first to query, so proceed carefully.
                # On non-NFS, information is coherent and we can simply proceed
                # comparing the DEV+INO information to see whether the file was
                # replaced.

                retry = False

                try:
                    st_fd = os.stat(fd)
                except OSError as e:
                    if e.errno != errno.ESTALE:
                        raise
                    retry = True

                try:
                    st_path = os.stat(path)
                except OSError as e:
                    if e.errno not in [errno.ENOENT, errno.ESTALE]:
                        raise
                    retry = True

                if retry or st_fd.st_dev != st_path.st_dev or st_fd.st_ino != st_path.st_ino:
                    linux.fcntl_flock(fd, linux.fcntl.F_UNLCK)
                    os.close(fd)
                    fd = None
                    continue

                # Yield control to the caller to make use of the FD. If the FD
                # is to be retained, clear it before returning to the cleanup
                # handlers.
                yield fd

                if not closefd:
                    fd = None

                return
        finally:
            if fd is not None:
                linux.fcntl_flock(fd, linux.fcntl.F_UNLCK)
                os.close(fd)

    @contextlib.contextmanager
    def _atomic_file(
        self,
        rpath: str,
        rpath_store: str,
        closefd: bool = True,
        ignore_exist: bool = False,
        replace: bool = False,
    ):
        """Create and link temporary file

        Create a new temporary file and yield control to the caller to fill in
        data and metadata. Once control is returned, the file is linked at the
        specified location. If an exception is raised, the temporary file is
        discarded.

        This function emulates the behavior of `O_TMPFILE` for systems and
        file-systems where it is not available.

        Parameters:
        -----------
        rpath
            Relative path from cache-root to the location where to link the
            file on success.
        rpath_store
            Relative path from cache-root to the store to use for temporary
            files. This must share the same mount-instance as the final path.
        closefd
            If false, retain file-descriptor (and lock) on success.
        ignore_exist
            If true, an existing file at the desired location during a
            replacement will not cause an error.
        replace
            If true, replace a previous file at the specified location. If
            false, no replacement takes place and the temporary file is
            discarded.
        """

        assert not replace or not ignore_exist

        rpath_tmp = None

        try:
            # First create a random file in the selected store. This file will
            # have a UUID as name and thus we can safely use `O_CREAT|O_EXCL`
            # to create it and guarantee its uniqueness.
            name = "uuid-" + uuid.uuid4().hex
            rpath_tmp = os.path.join(rpath_store, name)
            with self._atomic_open(
                rpath_tmp,
                wait=True,
                write=True,
                closefd=closefd,
                oflags=os.O_CREAT | os.O_EXCL,
            ) as fd:
                # Yield control to the caller to fill in data and metadata.
                with os.fdopen(fd, "r+", closefd=False, encoding="utf8") as file:
                    yield file

                suppress = []
                if ignore_exist:
                    suppress.append(errno.EEXIST)

                if replace:
                    # Move the file into the desired location, possibly
                    # replacing any existing entry.
                    os.rename(
                        src=self._path(rpath_tmp),
                        dst=self._path(rpath),
                    )
                else:
                    # Preferably, we used `RENAME_NOREPLACE`, but this is not
                    # supported on NFS. Instead, we create a hard-link, which
                    # will fail if the target already exists. We rely on the
                    # cleanup-path to drop the original link.
                    with ctx.suppress_oserror(*suppress):
                        os.link(
                            src=self._path(rpath_tmp),
                            dst=self._path(rpath),
                            follow_symlinks=False,
                        )
        finally:
            if rpath_tmp is not None:
                # If the temporary file exists, we delete it. If we haven't
                # created it, or if we already moved it, this will be a no-op.
                # Due to the unique name, we will never delete a file we do not
                # own. If we hard-linked the file, this merely deletes the
                # original temporary link.
                # On fatal errors, we leak the file into the object store. Due
                # to the released lock and UUID name, cache management will
                # clean it up.
                with ctx.suppress_oserror(errno.ENOENT):
                    os.unlink(self._path(rpath_tmp))

    def _atomic_dir(self, rpath_store: str) -> Tuple[str, int]:
        """Atomically create and lock an anonymous directory

        Create an anonymous directory in the specified storage directory
        relative to the cache-root. The directory will have a UUID as name. On
        success, the name of the directory and the open file-descriptor to its
        acquired lock file (write-locked) are returned.

        The lock-file logic follows the cache-logic for objects. Hence, the
        cache scaffolding for the specified store must exist. No other cache
        infrastructure is required, though.

        Parameters:
        -----------
        rpath_store
            Relative path from the cache-root to the storage directory to create
            the new anonymous directory in. Most likely, this is either the
            object-store or the staging-area.
        """

        rpath_dir = None
        rpath_lock = None

        try:
            while True:
                # Allocate a UUID for the new directory and prepare the paths
                # to the directory and lock-file inside.
                name = "uuid-" + uuid.uuid4().hex
                rpath_dir = os.path.join(rpath_store, name)
                rpath_lock = os.path.join(rpath_dir, self._filename_object_lock)

                # Create an anonymous lock-file, but before linking it create
                # the target directory to link the file in. Use an ExitStack
                # to control exactly where to catch exceptions.
                with contextlib.ExitStack() as es:
                    f = es.enter_context(
                        self._atomic_file(
                            rpath_lock,
                            rpath_store,
                            closefd=False,
                        )
                    )
                    lockfd = f.fileno()
                    os.mkdir(self._path(rpath_dir))

                    # Exit the `_atomic_file()` context, thus triggering a link
                    # of the anonymous lock-file into the new directory. A
                    # parallel cleanup might have deleted the empty directory,
                    # so catch `ENOENT` and retry.
                    try:
                        es.close()
                    except OSError as e:
                        if e.errno == errno.ENOENT:
                            continue
                        raise

                return (name, lockfd)
        except BaseException:
            # On error, we might have already created the directory or even
            # linked the lock-file. Try unlinking both, but ignore errors if
            # they do not exist. Due to using UUIDs as names we cannot conflict
            # with entries created by some-one else.
            if rpath_lock is not None:
                with ctx.suppress_oserror(errno.ENOENT, errno.ENOTDIR):
                    os.unlink(self._path(rpath_lock))
            if rpath_dir is not None:
                with ctx.suppress_oserror(errno.ENOENT, errno.ENOTDIR):
                    os.rmdir(self._path(rpath_dir))
            raise

    def _create_scaffolding(self):
        """Create cache scaffolding

        Create the directories leading to the cache, as well as the internal
        scaffolding directories and files. This ensures that an existing cache
        is not interrupted or rewritten. Hence, this can safely be called in
        parallel, even on live caches.

        If this happens to create a new cache, it is initialized with its
        default configuration and constraints. By default, this means the cache
        has a maximum size of 0 and thus is only used as staging area with no
        long-time storage.

        This call requires no cache-infrastructure to be in place, and can be
        called repeatedly at any time.
        """

        # Create the directory-scaffolding of the cache. Make sure to ignore
        # errors when they already exist, to allow for parallel setups.
        dirs = [
            self._path(self._dirname_objects),
            self._path(self._dirname_stage),
        ]
        for i in dirs:
            os.makedirs(i, exist_ok=True)

        # Create the file-scaffolding of the cache. We fill in the default
        # information and ignore racing operations.
        with self._atomic_file(self._filename_cache_tag, self._dirname_objects, ignore_exist=True) as f:
            f.write(
                "Signature: 8a477f597d28d172789f06886806bc55\n"
                "# This is a cache directory tag created by osbuild (see https://bford.info/cachedir/)\n"
            )
        with self._atomic_file(self._filename_cache_info, self._dirname_objects, ignore_exist=True) as f:
            json.dump({"version": self._version_current}, f)
        with self._atomic_file(self._filename_cache_lock, self._dirname_objects, ignore_exist=True) as f:
            pass
        with self._atomic_file(self._filename_cache_size, self._dirname_objects, ignore_exist=True) as f:
            f.write("0")

    def _load_cache_info(self, info: Optional[FsCacheInfo] = None):
        """Load cache information

        This loads information about the cache into this cache-instance. The
        cache-information is itself cached on this instance and only updated
        on request. If the underlying file in the cache changes at runtime it
        is not automatically re-loaded. Only when this function is called the
        information is reloaded.

        By default this function reads the cache-information from the
        respective file in the cache and then caches it on this instance. If
        the `info` argument is not `None`, then no information is read from the
        file-system, but instead the information is taken from the `info`
        argument. This allows changing the cache-information of this instance
        without necessarily modifying the underlying file.

        This call requires the cache scaffolding to be fully created.

        Parameters:
        -----------
        info
            If `None`, the cache info file is read. Otherwise, the information
            is taken from this tuple.
        """

        # Parse the JSON data into python.
        if info is None:
            with open(self._path(self._filename_cache_info), "r", encoding="utf8") as f:
                info_raw = json.load(f)

            info = FsCacheInfo.from_json(info_raw)

        # Retain information.
        self._info = info

        # Parse `maximum-size` into internal representation.
        if info.maximum_size == "unlimited":
            self._info_maximum_size = -1
        elif isinstance(info.maximum_size, int):
            self._info_maximum_size = info.maximum_size
        else:
            self._info_maximum_size = 0

    def _is_active(self):
        # Internal helper to verify we are in an active context-manager.
        return self._active

    def _is_compatible(self):
        # Internal helper to verify the cache-version is supported.
        return self._info.version is not None and \
            self._version_minimum <= self._info.version <= self._version_current

    def __enter__(self):
        assert not self._active

        try:
            # Acquire the current boot-id so we can tag entries accordingly, and
            # judge entries that are from previous boots.
            self._bootid = linux.proc_boot_id(self._appid).hex

            # Create the scaffolding for the entire cache.
            self._create_scaffolding()

            # Acquire a shared cache lock.
            self._lock = os.open(
                self._path(self._filename_cache_lock),
                os.O_RDONLY | os.O_CLOEXEC,
            )
            linux.fcntl_flock(self._lock, linux.fcntl.F_RDLCK, wait=True)

            # Read the cache configuration.
            self._load_cache_info()

            self._active = True
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, exc_type, exc_value, exc_tb):
        # Discard any state of this context and reset to original state.
        if self._lock is not None:
            linux.fcntl_flock(self._lock, linux.fcntl.F_UNLCK)
            os.close(self._lock)
            self._lock = None
        self._active = False
        self._bootid = None
        self._info = FsCacheInfo()
        # We always have to leave the file-system scaffolding around. Even if
        # the cache is entirely empty, we cannot know whether there are other
        # parallel accesses (without unreasonable effort).

    def _update_cache_size(self, diff: int) -> bool:
        """Update cache size

        Update the total cache size by the specified amount, unless it exceeds
        the cache limits.

        This carefully updates the stored cache size to allow for parallel
        updates by other cache users. If the cache limits are exceeded, the
        operation is canceled and `False` is returned. Otherwise, `True` is
        returned.

        If the specified amount is negative, the operation always succeeds. If
        the cache size would end up negative, it is capped at 0.

        This operation requires an active context.
        """

        assert self._is_active()
        assert self._is_compatible()

        # Open the cache-size and lock it for writing. But instead of writing
        # directly to it, we replace it with a new file. This guarantees that
        # we cannot crash while writing a partial size, but always atomically
        # update the content.
        with self._atomic_open(self._filename_cache_size, write=True, wait=True) as fd:
            with os.fdopen(fd, "r", closefd=False, encoding="utf8") as f:
                size = json.load(f)

            if size + diff < 0:
                size = 0
            elif (self._info_maximum_size < 0) or (size + diff <= self._info_maximum_size):
                size = size + diff
            else:
                return False

            with self._atomic_file(self._filename_cache_size, self._dirname_objects, replace=True) as f:
                json.dump(size, f)

            return True

    def _rm_r_object(self, rpath_dir: str):
        """Remove object

        Recursively remove all traces of a stored object. This either requires
        the caller to hold a write-lock on the entry, or otherwise guarantee
        that no cache lookups can acquire the entry concurrently.

        This carefully deletes any traces of the entry, making sure to first
        mark the object as invalid, and dropping the lock-file last. This can
        safely be called on partially constructured or non-existing entries.

        Parameters:
        -----------
        rpath_dir
            Relative path from the cache-root to the object directory.
        """

        path_dir = self._path(rpath_dir)
        path_info = os.path.join(path_dir, self._filename_object_info)
        path_lock = os.path.join(path_dir, self._filename_object_lock)

        # Optimization: Bail out early if the entry is non-existant
        if not os.path.lexists(path_dir):
            return

        # First step, we unlink the info-file. This will mark the entry as
        # volatile and thus it will get cleaned up by cache management in case
        # we crash while deleting it. Furthermore, no cache lookups will ever
        # consider the entry again if the info-file is missing.
        with ctx.suppress_oserror(errno.ENOENT, errno.ENOTDIR):
            os.unlink(path_info)

        # Now iterate the directory and drop everything _except_ the lock file.
        # This makes sure no parallel operation will needlessly race with us. In
        # case no lock is acquired, we still allow for parallel racing cleanups.
        #
        # Note that racing cleanups might delete the entire directory at any
        # time during this iteration. Furthermore, `scandir()` is not atomic but
        # repeatedly calls into the kernel. Hence, we carefully bail out once
        # it reports a non-existant directory.
        with ctx.suppress_oserror(errno.ENOENT, errno.ENOTDIR):
            for entry in os.scandir(path_dir):
                if entry.name == self._filename_object_lock:
                    continue
                with ctx.suppress_oserror(errno.ENOENT, errno.ENOTDIR):
                    if entry.is_dir():
                        rmrf.rmtree(entry.path)
                    else:
                        os.unlink(entry.path)

        # With everything gone, we unlink the lock-file and eventually delete
        # the directory. Again, cleanup routines might have raced us, so avoid
        # failing in case the entries are already gone.
        with ctx.suppress_oserror(errno.ENOENT, errno.ENOTDIR):
            os.unlink(path_lock)
        with ctx.suppress_oserror(errno.ENOENT, errno.ENOTDIR):
            os.rmdir(path_dir)

    @contextlib.contextmanager
    def stage(self):
        """Create staging entry

        Create a new entry in the staging area and yield control to the caller
        with the relative path to the entry. Once control returns, the staging
        entry is completely discarded.

        If the application crashes while holding a staging entry, it will be
        left behind in the staging directory, but unlocked and marked as stale.
        Hence, any cache management routine will discard it.
        """

        # We check for an active context, but we never check for
        # version-compatibility, because there is no way we can run without
        # a staging area. Hence, the staging-area has to be backwards
        # compatible at all times.
        assert self._is_active()

        uuidname = None
        lockfd = None

        try:
            # Create and lock a new anonymous object in the staging area.
            uuidname, lockfd = self._atomic_dir(self._dirname_stage)

            rpath_data = os.path.join(
                self._dirname_stage,
                uuidname,
                self._dirname_data,
            )

            # Prepare an empty data directory and yield it to the caller.
            os.mkdir(self._path(rpath_data))
            yield rpath_data
        finally:
            if lockfd is not None:
                self._rm_r_object(os.path.join(self._dirname_stage, uuidname))
                linux.fcntl_flock(lockfd, linux.fcntl.F_UNLCK)
                os.close(lockfd)

    @contextlib.contextmanager
    def store(self, name: str):
        """Store object in cache

        Create a new entry and store it in the cache with the specified name.
        The entry is first created with an anonymous name and control is yielded
        to the caller to fill in data. Once control returns, the entry is
        committed with the specified name.

        The final commit is skipped if an entry with the given name already
        exists, or its name is claimed for other reasons. Furthermore, the
        commit is skipped if cache limits are exceeded, or if cache maintenance
        refuses the commit. Hence, a commit can never be relied upon and the
        entry might be deleted from the cache as soon as the commit was invoked.

        Parameters:
        -----------
        name
            Name to store the object under.
        """

        assert self._is_active()
        assert self._bootid is not None

        if not name:
            raise ValueError()

        # If the cache-version is incompatible to this implementation, we short
        # this call into the staging-area (which is always compatible). This
        # avoids raising an exception (at the cost of dealing with this in the
        # caller), and instead just creates a temporary copy which we discard.
        if not self._is_compatible():
            with self.stage() as p:
                yield p
            return

        uuidname = None
        lockfd = None

        try:
            # Create and lock a new anonymous object in the staging area.
            uuidname, lockfd = self._atomic_dir(self._dirname_objects)

            rpath_uuid = os.path.join(
                self._dirname_objects,
                uuidname,
            )
            rpath_data = os.path.join(
                rpath_uuid,
                self._dirname_data,
            )
            rpath_info = os.path.join(
                rpath_uuid,
                self._filename_object_info,
            )
            path_uuid = self._path(rpath_uuid)
            path_data = self._path(rpath_data)
            path_info = self._path(rpath_info)

            # Prepare an empty data directory and yield it to the caller.
            os.mkdir(path_data)
            yield rpath_data

            # Collect metadata about the new entry.
            info: Dict[str, Any] = {}
            info["creation-boot-id"] = self._bootid
            info["size"] = self._calculate_size(path_data)

            # Update the total cache-size. If it exceeds the limits, bail out
            # but do not trigger an error. It behaves as if the entry was
            # committed and immediately deleted by racing cache management. No
            # need to tell the caller about it (if that is ever needed, we can
            # provide for it).
            #
            # Note that if we crash after updating the total cache size, but
            # before committing the object information, the total cache size
            # will be out of sync. However, it is never overcommitted, so we
            # will never violate any cache invariants. The cache-size will be
            # re-synchronized by any full cache-management operation.
            if not self._update_cache_size(info["size"]):
                return

            try:
                # Commit the object-information, thus marking it as fully
                # committed and accounted in the cache.
                with open(path_info, "x", encoding="utf8") as f:
                    json.dump(info, f)

                # As last step move the entry to the desired location. If the
                # target name is already taken, we bail out and pretend the
                # entry was immediately overwritten by another one.
                #
                # Preferably, we used RENAME_NOREPLACE, but this is not
                # available on all file-systems. Hence, we rely on the fact
                # that non-empty directories cannot be replaced, so we
                # automatically get RENAME_NOREPLACE behavior.
                path_name = self._path(self._dirname_objects, name)
                try:
                    os.rename(
                        src=path_uuid,
                        dst=path_name,
                    )
                except OSError as e:
                    ignore = [errno.EEXIST, errno.ENOTDIR, errno.ENOTEMPTY]
                    if e.errno not in ignore:
                        raise

                uuidname = None
            finally:
                # If the anonymous entry still exists, it will be cleaned up by
                # the outer handler. Hence, make sure to drop the info file
                # again and de-account it, so we don't overcommit.
                if os.path.lexists(path_uuid):
                    with ctx.suppress_oserror(errno.ENOENT, errno.ENOTDIR):
                        os.unlink(path_info)
                    self._update_cache_size(-info["size"])
        finally:
            if lockfd is not None:
                if uuidname is not None:
                    # In case this runs after the object was renamed, but before
                    # `uuidname` was cleared, then `_rm_r_object()` will be a
                    # no-op.
                    self._rm_r_object(os.path.join(self._dirname_objects, uuidname))
                linux.fcntl_flock(lockfd, linux.fcntl.F_UNLCK)
                os.close(lockfd)

    @contextlib.contextmanager
    def load(self, name: str):
        """Load a cache entry

        Find the cache entry with the given name, acquire a read-lock and
        yield its path back to the caller. Once control returns, the entry
        is released.

        The returned path is the relative path between the cache and the top
        level directory of the cache entry.

        Parameters:
        -----------
        name
            Name of the cache entry to find.
        """

        assert self._is_active()

        if not name:
            raise ValueError()
        if not self._is_compatible():
            raise self.MissError()

        with contextlib.ExitStack() as es:
            # Use an ExitStack so we can catch exceptions raised by the
            # `__enter__()` call on the context-manager. We want to catch
            # `OSError` exceptions and convert them to cache-misses.
            try:
                es.enter_context(
                    self._atomic_open(
                        os.path.join(
                            self._dirname_objects,
                            name,
                            self._filename_object_lock,
                        ),
                        write=False,
                        wait=False,
                    )
                )
            except OSError as e:
                if e.errno in [errno.EAGAIN, errno.ENOENT, errno.ENOTDIR]:
                    raise self.MissError() from None
                raise e

            yield os.path.join(
                self._dirname_objects,
                name,
                self._dirname_data,
            )

    @property
    def info(self) -> FsCacheInfo:
        """Query Cache Information

        Return the parsed cache information which is currently cached on this
        cache-instance. The cache information has all unknown fields stripped.

        Unset values are represented by `None`, and the cache will interpret
        it as the default value for the respective field.
        """

        assert self._is_active()

        return self._info

    @info.setter
    def info(self, info: FsCacheInfo):
        """Write Cache Information

        Update and write the cache-information onto the file-system. This first
        locks the cache-information file, reads it in, updates the newly read
        information with the data from `info`, writes the result back to disk
        and finally unlocks the file.

        There are a few caveats to take into account:

         * The locking guarantees that simultaneous updates will be properly
           ordered and never discard any information.
         * Since this reads in the newest cache-information, this function can
           update cache-information values other than the ones from `info`. Any
           value unset in `info` will be re-read from disk and thus might
           change (in the future, if required, this can be adjusted to allow a
           caller to hook into the operation while the lock is held).
         * You cannot strip known values from the cache-information. Any value
           not present in `info` is left unchanged. You must explicitly set a
           value to its default to reset it.
         * Cache-information fields that are not known to this implementation
           are never exposed to the caller, but are left unchanged on-disk.
           This guarantees that future extensions are left alone and are not
           accidentally stripped.

        The cached information of this instance is updated to reflect the
        changes.

        Parameters:
        -----------
        info
            Cache information object to consume and write.
        """

        assert self._is_active()

        with self._atomic_open(self._filename_cache_info, write=True, wait=True) as fd:
            with os.fdopen(fd, "r", closefd=False, encoding="utf8") as f:
                info_raw = json.load(f)

            # If the on-disk data is in an unexpected format, we never touch
            # it. If it is a JSON-object, we update it with the new values and
            # then re-parse it into a full `FsCacheInfo` with all known fields
            # populated.
            if isinstance(info_raw, dict):
                info_raw.update(info.to_json())
                info = FsCacheInfo.from_json(info_raw)

                # Replace the file with the new values. This releases the lock.
                if self._is_compatible():
                    with self._atomic_file(self._filename_cache_info, self._dirname_objects, replace=True) as f:
                        json.dump(info_raw, f)

        self._load_cache_info(info)

    def store_tree(self, name: str, tree: Any):
        """Store file system tree in cache

        Create a new entry in the object store containing a copy of the file
        system tree specified as `tree`. This behaves like `store()` but instead
        of providing a context to the caller it will copy the specified tree.

        Similar to `store()`, when the entry is committed it is immediately
        unlocked and released to the cache. This means it might vanish at any
        moment due to a parallel cleanup. Hence, a caller cannot rely on the
        object being available in the cache once this call returns.

        If `tree` points to a file, the file is copied. If it points to a
        directory, the entire directory tree is copied including the root entry
        itself. To copy an entire directory without its root entry, use the
        `path/.` notation. Links are never followed but copied verbatim.
        All metadata is preserved, if possible.

        Parameters:
        -----------
        name
            Name to store the object under.
        tree:
            Path to the file system tree to copy.
        """

        with self.store(name) as rpath_data:
            r = subprocess.run(
                [
                    "cp",
                    "--reflink=auto",
                    "-a",
                    "--",
                    os.fspath(tree),
                    self._path(rpath_data),
                ],
                check=False,
                encoding="utf-8",
                stderr=subprocess.STDOUT,
                stdout=subprocess.PIPE,
            )
            if r.returncode != 0:
                code = r.returncode
                msg = r.stdout.strip()
                raise RuntimeError(f"Cannot copy into file-system cache ({code}): {msg}")
