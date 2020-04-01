"""Path Descriptor

This module implements a path object based on the `O_PATH` file descriptors
provided by the linux kernel. It does automatic file-descriptor management and
thus simplifies handling of `O_PATH` quite significantly.

Classic path handling uses strings as internal state. This includes python
modules like `os.path` or `pathlib`. However, these have major drawbacks,
including the following:

  * File-system paths have to be resolved on each access. This makes
    repeated access to the same path (or a sibling path) racy and non-reliable.
    For instance, accessing `/foo/bar/A` and `/foo/bar/B` consequetively might
    end up with files from different directories, even though their path
    suggests that they are siblings. This can happen for many reasons. Simply
    imagine `/foo/bar` is a symlink and it is changed between the consequetive
    operations. Another possibility is modifying local mounts.
    While this behavior is not necessarily wrong, it is more often than not
    contrary to the intended behavior. By using path-descriptors, you can
    operate relative to pinned paths, thus picking the point of reference
    manually, rather than using the root path (or local mount, or working
    directory).

  * Resolving a file-system path relies on ambient capabilities. The most
    prominent examples are paths relative to the current working directory. If
    the current working directory changes between accesses, your relative paths
    will as well.
    Again, this is not necessarily bad, but it might not be what you expect. In
    fact, the path-descriptors provide exactly the same functionality as the
    current working directory of a process. However, instead of having only one
    static property as part of a process, path-descriptors are objects that can
    be created and modified at will by the program.

  * Status queries on file-system objects like `stat()` suffer from TOCTOU
    races. These can be solved via their fd-based counterparts like `fstat()`,
    but that requires opening the file either for at least reading or writing.
    But this is not necessarily what you want, since you might not have read or
    write access (and unlike `stat()` your operation might not necessarily
    require either access right).
    With path-descriptors you can refer to paths in a stable manner without
    requiring read nor write access to the path.

  * ...

The path-descriptors are functionally superior to normal string-based path
objects, but not necessarily the better option in all situations. Their
flexibility and stable behavior is a big strength, but their biggest weakness
is the overhead involved in all the syscalls to manage them. They are based on
`O_PATH` file-descriptor, rather than simple strings, and thus require syscalls
for every single operation. In many situations these additional syscalls
amortize easily, but that has to be evaluated for every situation separately.

Please be aware that path-descriptors are not suitable for access management!
Access to a path-descriptor does **NOT** restrict the access you gain via it.
You can always use relative operations on the path-descriptor to access its
parents, children, and any other part of the file-system reachable from that
path.
You can, however, combine path-descriptors with other technology to achieve
access restrictions. This implementation allows for this, but considers the
discussion of this topic beyond the scope of this module.
"""


import errno as _errno
import os as _os
import stat as _stat


__all__ = [
    "PathFd",
]


class PathFd:
    """Path Descriptor

    A path-descriptor object is a representation of a file-system path. Every
    instance represents exactly one path. Internally, every instance owns its
    backing `O_PATH` file-descriptor, which pins the capability of referring to
    the path it represents.

    For a discussion of when to use path-descriptors over simple paths, see the
    `O_PATH` functionality provided by linux. This path-descriptor simply
    provides easy access to `O_PATH` file-descriptors.

    Since path-descriptors manage resources, they do provide the standard
    resource management operations. This means, `close()` releases all internal
    resources and turns the instance into a no-op stub. Further operations on
    the stub will trigger assertions. This follows what the python standard
    library provides, and thus integrates well with context-managers (a default
    context manager is provided with the implementation, but
    `contextlib.closing()` would also work.
    Note that there is no requirement to call `close()`. The only reason to do
    so is to keep resource management under caller-control if they so wish. If
    the GC cleanup is enough for you, then you can avoid calling `close()`. But
    if you want to avoid having stale resources pile up until the next GC
    round, then you better close your objects when no longer needed.
    The internal operations of this module always clean up all their temporary
    resources explicitly to avoid this problem.
    """

    _fd = None

    def __init__(self, fd = None):
        """Initialize Path Descriptor

        This creates a new path-descriptor by taking a caller-provided `O_PATH`
        file-descriptor and consuming it.

        Parameters
        ----------
        fd : int, None
            A raw file descriptor to use for this path descriptor. This must be
            a file-descriptor opened with `O_PATH`. This function consumes this
            file-descriptor. That is, regardless whether this function succeeds
            or fails, it does take full control of the file-descriptor. The
            caller must not access the original file-descriptor, anymore.
            Pass `None` to create a path descriptor that is already closed.
        """

        assert (fd is None) or (fd >= 0)

        self._fd = fd

    @classmethod
    def from_path(cls, path, *, follow_symlink = False):
        """Create Path Descriptor from File System Path

        This constructor creates a new path-descriptor from a standard
        file-system path provided as a string. It simply opens the path as
        `O_PATH` file-descriptor and creates a wrapping path-descriptor around
        it. Path resolution happens at the time of this function call. All
        further operations on the new path-descriptor will happen relative to
        the desciptor itself. The contents of `path` are not retained and will
        not be accessible later on.

        Parameters
        ----------
        path : String
            A file-system path in string representation. If it is a relative
            path, it is interpreted relative to the current working directory
            at the time of this function call.
        follow_symlink : Boolean, optional
            Whether to resolve the final part of the path in case it is a
            symlink. The default behavior is to not resolve it. That is, if the
            given path points to a symlink, the path-descriptor will also point
            to the symlink, rather than pointing to the destination of that
            symlink.
            This does not affect symlinks somewhere else in the path, other
            than the last element.

        Returns
        -------
        PathFd
            A new path-desciptor for the specified path is returned.

        Raises
        ------
        OSError
            Any operating system errors involved in resolving file-system paths
            can be raised by this function. See `os.open()` in the python
            standard library for a discussion.
        """
        flags = _os.O_CLOEXEC | _os.O_PATH
        if not follow_symlink:
            flags |= _os.O_NOFOLLOW

        return PathFd(_os.open(path, flags))

    def close(self):
        """Close the Path Descriptor

        This closes the path-descriptor and releases all pinned resources. Once
        this returns, any further operation on the path-descriptor will raise
        an exception, unless it is explictily supported on closed descriptors.

        This function can be safely called on closed descriptors, in which case
        it is a no-op.
        """

        if self._fd is not None:
            _os.close(self._fd)
            self._fd = None

    def __del__(self):
        # Make sure to release internal resources when variables of this type
        # are cleaned up by the GC. In case they were already explicitly closed
        # this will be a no-op.
        self.close()

    def __enter__(self):
        # Trivial context-manager ala `contextlib.closing()`.
        return self

    def __exit__(self, *args):
        # Trivial context-manager ala `contextlib.closing()`.
        self.close()

    def __int__(self):
        """Convert to Integer

        Convert the path-descriptor into a file-descriptor. The file-descriptor
        is only borrowed. It is still owned by the path-descriptor, so you must
        not close it manually.

        This raises an exception if the path-descriptor is already closed.

        Returns
        -------
        int
            An integer greater than, or equal to, zero is returned.
        """

        assert self._fd is not None

        return self._fd

    def is_open(self):
        """Check whether the Path Descriptor is Open

        This simply returns a boolean that tells whether the descriptor is
        still open. Note that once a descriptor is closed, it cannot be
        re-opened. You must create a new descriptor to do that.

        This can be safely called on closed descriptors.

        Returns
        -------
        Boolean
            Whether the descriptor is open. This is true for all descriptors
            until they are closed via `close()`, or if they were created as a
            closed descriptor.
        """

        return self._fd is not None

    def clone(self):
        """Create a Clone

        This clones the given path-descriptor and returns it. The cloned
        instance will point to the exact same resource as the original, without
        re-resolving the path.

        The original and the cloned instance do not share any underlying
        resources. They are fully independent.

        This can be safely called on closed descriptors, in which case the
        cloned instance will also be closed.

        Returns
        -------
        PathFd
            A new path-desciptor for the same path is returned.

        Raises
        ------
        OSError
            Any operating system errors involved in duplicating
            file-descriptors can be raised by this function. See `os.dup()` for
            a discussion of possible errors.
        """

        if self.is_open():
            return PathFd(_os.dup(int(self)))
        else:
            return PathFd()

    def stat(self):
        """Query File System Stat-Information

        This performs the `fstat(2)` syscall on the file-system resource this
        path-descriptor points to.

        This is safe against TOCTOU races. Repeated calls are guaranteed to
        return the same information, unless the information itself got changed
        in the meantime.

        This function does not cache any results. Every call results in a new
        syscall invocation.

        Note that this does not perform any path resolution. It accesses
        exactly the resource the descriptor points to. If it points to a
        symlink, it will return information for that symlink, rather than
        information for the object the symlink points to. You must resolve
        symlinks when creating a path-descriptor, in case you want symlinks
        resolved.

        Returns
        -------
        stat_result
            The file-system information is reported as a return value of the
            `stat_result` type from the python standard library.

        Raises
        ------
        OSError
            See the python standard library for possible errors when querying
            stat-information (e.g., `os.stat()`).
        """

        assert self.is_open()

        return _os.fstat(int(self))

    def is_directory(self):
        """Check whether the Path is a Directory

        This is a convenience wrapper around `stat()` which checks whether the
        path is a directory. This simply checks for `S_ISDIR()` on the
        `st_mode` field of the file-system stat-information.

        Returns
        -------
        Boolean
            Whether the file-system object this descriptor points to is a
            directory.

        Raises
        ------
        OSError
            See the python standard library for possible errors when querying
            stat-information (e.g., `os.stat()`).
        """

        assert self.is_open()

        return _stat.S_ISDIR(self.stat().st_mode)

    def is_symlink(self):
        """Check whether the Path is a Symlink

        This is a convenience wrapper around `stat()` which checks whether the
        path is a symlink. This simply checks for `S_ISLNK()` on the
        `st_mode` field of the file-system stat-information.

        Returns
        -------
        Boolean
            Whether the file-system object this descriptor points to is a
            symlink.

        Raises
        ------
        OSError
            See the python standard library for possible errors when querying
            stat-information (e.g., `os.stat()`).
        """

        assert self.is_open()

        return _stat.S_ISLNK(self.stat().st_mode)

    def open_relative(self, path, flags, mode = 0o777):
        """Open Relative Path

        Open a path relative to this path-descriptor. This simply wraps the
        `os.open()` call of the python standard-library, but as an
        object-oriented call on a path-descriptor.

        This behaves like `os.open()` of the python standard library, but uses
        the path-descriptor as `dif_fd` argument.

        If the given path is absolute, it will be based off the file-system
        root rather than the path-descriptor this is called on.

        This function always forces `O_CLOEXEC`. You must clear it afterwards,
        if that is what you want.

        Parameters
        ----------
        path : String
            A file-system path in string representation. If it is a relative
            path, it is interpreted relative to the path-descriptor this
            function is called on.
        flags : int
            The open-flags to pass to `os.open()`.
        mode : int, optional
            The file creation flags to use with `os.open()`. Defaults to
            `0o777`, but is subject to the current umask.

        Returns
        -------
        int
            The syscall result of `open(2)` is returned. This is usually a
            file-descriptor.

        Raises
        ------
        OSError
            See the python standard library for possible errors when opening
            paths (e.g., `os.open()`).
        """

        assert self.is_open()

        flags |= _os.O_CLOEXEC
        return _os.open(path, flags, mode, dir_fd = int(self))

    def open_self(self, flags, mode = 0o777):
        """Open own Path

        Open the file-system object this path-descriptor points to. This wraps
        the `os.open()` call from the python standard library, but hard-codes
        the path to the object this path-descriptor points to.

        Unfortunately, for obscure legacy reasons the linux kernel does not
        provide the `AT_EMPTY_PATH` equivalent for `open(2)`. This means, you
        cannot directly open a path-descriptor, but have to redirect via
        `/proc/self/fd/<fd>`. Hence, this is what this implementation does.
        This is, however, not strictly equivalent to opening the
        path-descriptor directly. Therefore, some features are blocked to avoid
        exposing broken behavior:

          * You cannot use `O_NOFOLLOW` with this, as it would open the symlink
            in `/proc` rather than the object the descriptor points to (and
            because you cannot open symlinks, it would fail). Hence, passing
            `O_NOFOLLOW` will raise an exception.
            If you want this behavior, you must check via `is_symlink()`
            manually, and then call this without `O_NOFOLLOW`.

          * This relies on `/proc` being a proper `procfs` file-system. This
            is the case for all known linux systems. If you use non-standard
            setups, you must be aware that this call will fail, unless `/proc`
            is properly setup (or worse if you re-use `/proc` for other
            things).

        This function always forces `O_CLOEXEC`. You must clear it afterwards,
        if that is what you want.

        Parameters
        ----------
        flags : int
            The open-flags to pass to `os.open()`.
        mode : int, optional
            The file creation flags to use with `os.open()`. Defaults to
            `0o777`, but is subject to the current umask.

        Returns
        -------
        int
            The syscall result of `open(2)` is returned. This is usually a
            file-descriptor.

        Raises
        ------
        OSError
            See the python standard library for possible errors when opening
            paths (e.g., `os.open()`).
        """

        #
        # Preferably, we would want to use `openat(self, "", ... O_EMPTYPATH)`,
        # but sadly there is no `AT_EMPTY_PATH` equivalent for `openat(2)`.
        # Instead, we must go the route via `/proc`.
        # Note that for questionable security reasons the `O_EMPTYPATH` flag is
        # unlikely to appear at all (also see `AT_EMPTY_PATH` in `linkat(2)`
        # for a discussion).
        #
        # We simply block the `O_NOFOLLOW` flag to make sure callers will not
        # accidentally end up opening a file in `/proc`. If you want
        # `O_NOFOLLOW` with `open_self()`, you are left with checking through
        # `is_symlink()` before calling `open_self()` without `O_NOFOLLOW`.
        # Note that this is safe as long as you call it on the same `DirFd`.
        #

        assert self.is_open()
        assert not (flags & _os.O_NOFOLLOW)

        flags |= _os.O_CLOEXEC
        path = _os.path.join("/proc/self/fd/", str(int(self)))

        return _os.open(path, flags, mode)

    def descend(self, path, *, follow_symlink = False):
        """Create Descendent

        Create a new path-descriptor relative to this path-descriptor. The
        given path is resolved at the time of this function call, and the new
        descriptor will point to the file-system object it refers to.

        Note that if your descriptor is an absolute path, it will not use the
        path-descriptor as relative anchor, but instead be based off the
        file-system root.

        Also see `from_path()` for the equivalent of this call but relative to
        the current working directory.

        Parameters
        ----------
        path : String
            A file-system path in string representation. If it is a relative
            path, it is interpreted relative to the path-descriptor this
            function is called on.
        follow_symlink : Boolean, optional
            Whether to resolve the final part of the path in case it is a
            symlink. The default behavior is to not resolve it.

        Returns
        -------
        PathFd
            A new path-desciptor for the specified path is returned.

        Raises
        ------
        OSError
            Any operating system errors involved in resolving file-system paths
            can be raised by this function. See `os.open()` in the python
            standard library for a discussion.
        """

        assert self.is_open()

        flags = _os.O_CLOEXEC | _os.O_PATH
        if not follow_symlink:
            flags |= _os.O_NOFOLLOW

        return PathFd(self.open_relative(path, flags))

    def enumerate(self, *, follow_symlink = False, fn_open_self = open_self, fn_descend = descend):
        """Enumerate Directory Entries

        Create a generator that enumerates the directory entries below the
        directory pointed to by this path-descriptor. Effectively, this calls
        `os.scandir()` on this path-descriptor and returns all entries. Unlike
        a normal directory listing, this returns a path-descriptor for each
        entry, as well as the `os.DirEntry` object as defined by the python
        standard library.

        This function will raise an exception if the path-descriptor does not
        point to a directory, or is already closed.

        Listing directory entries is not necessarily atomic. For instance, on
        linux the `getdents(2)` system call has to be called repeatedly to
        enumerate an entire directory. There is no guarantee that a single call
        will suffice. Therefore, no atomicity guarantees are given. At the time
        an entry is returned by the generator, it might have already been
        unlinked or moved (regardless of this, the returned path-descriptor is
        always valid). Furthermore, if new entries are created in the directory
        while an enumeration is ongoing, there is no guarantee that it will
        show up in the enumeration. For details on the behavior of parallel
        file-system modifications, consult your operating system manuals.

        This function diligently avoids race conditions between listing a
        directory entry and opening a path-descriptor to it. It guarantees
        coherent behavior and catches common errors. This means, the returned
        directory entries are guaranteed to be valid entries you can operate
        on.

        Internally, this function first opens the directory to enumerate, then
        iterates it and opens a path-descriptor for each entry. It allows the
        caller to override the functions used to open the directory and to open
        the path-descriptors. This way, callers can catch specific `OSError`
        exceptions and modify the behavior. A common scenario is catching
        access permissions and then modifying the access rights before retrying
        the operation (this is particularly useful when iterating for deletion).
        If you override these functions, you must provide the same invariants
        as the originals do. You usually achieve this by calling into the
        originals from your functions, and simply extending their
        functionality, rather than reimplementing it.

        Parameters
        ----------
        follow_symlink : Boolean, optional
            Whether to resolve symlink entries. Default behavior is not to
            resolve them.
        fn_open_self : Function, optional
            Override the function used to open the directory. By default,
            this uses the `open_self()` method on path-descriptors.
        fn_descend : Function, optional
            Override the function used to open directory entries. By default,
            this uses the `descend()` method on path-descriptors.

        Returns
        -------
        Generator
            A generator that produces tuples of a path-descriptor and an
            `os.DirEntry` object is returned.

        Raises
        ------
        OSError
            This can raise an `OSError` if the original directory cannot be
            opened for enumeration. Furthermore, this might raise further
            errors if the entries cannot be opened via `O_PATH` (e.g., lacking
            directory execution rights).
        """

        assert self.is_open()

        # You can open path-descriptors which point to directories even if the
        # directory was removed. This call should always succeed, except for
        # wrong setups, access restrictions, or programming errors.
        flags = _os.O_RDONLY | _os.O_CLOEXEC | _os.O_DIRECTORY
        dir_fd = fn_open_self(self, flags)

        # Reading from a directory might fail for several reasons. Since
        # reading is not atomic and might be chunked, each call that fetches
        # directory entries might fail for these reasons.
        #
        #   * ENOENT: If the parent directory is empty and then was dropped via
        #             `rmdir(2)`, we will get `ENOENT`.
        #
        # No other possible error-scenarios are known at this time. This might
        # need extension in the future, though.
        readdir_break_on = [ _errno.ENOENT ]

        entries = None
        try:
            entries = _os.scandir(dir_fd)
        except OSError as e:
            # This operation should be a no-op, but python does not guarantee
            # it. Technically, this might call `readdir()` (or `getdents(2)`)
            # so we treat it the same as reading from the `entries` iterator.
            if not any(e.errno == i for i in readdir_break_on):
                raise e
        else:
            while True:
                entry = None
                try:
                    # This calls `readdir()` (or probably the improved version
                    # of it: `getdents(2)`). It very linkely is a batched
                    # operation, so not each call will end up in a syscall.
                    entry = next(entries)
                except StopIteration:
                    break
                except OSError as e:
                    # See discussion above on `os.scandir()` for exceptions.
                    if any(e.errno == i for i in readdir_break_on):
                        break
                    else:
                        raise e

                try:
                    with fn_descend(self, entry.name, follow_symlink = follow_symlink) as pathfd:
                        yield (pathfd, entry)
                except OSError as e:
                    if e.errno == _errno.ENOENT:
                        # A file might very well get deleted in between listing
                        # the directory entries and trying to access it. We can
                        # safely ignore this and pretend the directory listing
                        # was chunked differently and never returned this
                        # unlinked file.
                        continue
                    else:
                        raise e
        finally:
            if entries is not None:
                entries.close()
            _os.close(dir_fd)

    def traverse(self, *, postorder = False, fn_enumerate = enumerate):
        """Traverse Directory Tree

        This creates a generator that iteratively traverses a directory tree,
        yielding an object for every entry in that file-system tree. It
        operates through `enumerate()` internally, but traveses an entire tree
        rather than just a single directory level.

        Note that `follow_symlink` is not provided as an option, and this
        function currently behaves as if it was set to `False`. Traversing a
        tree and following symlinks easily deadlocks. Furthermore, the
        semantics are not entirely clear. Therefore, it is left to the caller
        to resolve symlinks, if they so desire.

        No entry for the object this is called on is yielded. That is, if the
        directory that `self` points to is empty, this will yield no entries.

        Parameters
        ----------
        postorder : Boolean, optional
            Whether to yield entries in postorder. Default behavior is
            preorder. That is, in preorder mode a directory is yielded before
            the entries of the directory are yielded. In postorder mode, this
            behavior is reversed.
        fn_enumerate : Function, optional
            Override the function used to enumerate a directory. By default,
            this uses the `enumerate()` method on path-descriptors.

        Returns
        -------
        Generator
            A generator that produces tuples of a path-descriptor and an
            `os.DirEntry` object is returned. Note that the directory entry
            only contains information for the level it is on. No information
            about the parent directories is included.

        Raises
        ------
        OSError
            This uses `enumerate()` internally, and thus returns the same set
            of errors. No additional considerations apply.
        """

        assert self.is_open()

        # We use a non-recursive implementation that stores every directory we
        # recurse into on the stack, and pops it once fully enumerated.
        stack = [ (self, None, fn_enumerate(self)) ]

        while len(stack) > 0:
            (current_dirfd, current_entry, current_scan) = stack[-1]

            for (sub_dirfd, sub_entry) in current_scan:
                if sub_dirfd.is_directory():
                    if not postorder:
                        yield (sub_dirfd, sub_entry)

                    stack.append((sub_dirfd, sub_entry, fn_enumerate(sub_dirfd)))
                    break
                else:
                    yield (sub_dirfd, sub_entry)
            else:
                if postorder and (current_entry is not None):
                    yield (current_dirfd, current_entry)

                stack.pop()
