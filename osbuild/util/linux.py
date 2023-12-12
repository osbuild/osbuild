"""Linux API Access

This module provides access to linux system-calls and other APIs, in particular
those not provided by the python standard library. The idea is to provide
universal wrappers with broad access to linux APIs. Convenience helpers and
higher-level abstractions are beyond the scope of this module.

In some cases it is overly complex to provide universal access to a specific
API. Hence, the API might be restricted to a reduced subset of its
functionality, just to make sure we can actually implement the wrappers in a
reasonable manner.
"""


import array
import ctypes
import ctypes.util
import fcntl
import hashlib
import hmac
import os
import platform
import struct
import threading
import uuid

__all__ = [
    "fcntl_flock",
    "ioctl_get_immutable",
    "ioctl_toggle_immutable",
    "Libc",
    "proc_boot_id",
]


# NOTE: These are wrong on at least ALPHA and SPARC. They use different
#       ioctl number setups. We should fix this, but this is really awkward
#       in standard python.
#       Our tests will catch this, so we will not accidentally run into this
#       on those architectures.
FS_IOC_GETFLAGS = 0x80086601
FS_IOC_SETFLAGS = 0x40086602

FS_IMMUTABLE_FL = 0x00000010


if platform.machine() == "ppc64le":
    BLK_IOC_FLSBUF = 0x20001261
else:
    BLK_IOC_FLSBUF = 0x00001261


def ioctl_get_immutable(fd: int):
    """Query FS_IMMUTABLE_FL

    This queries the `FS_IMMUTABLE_FL` flag on a specified file.

    Arguments
    ---------
    fd
        File-descriptor to operate on.

    Returns
    -------
    bool
        Whether the `FS_IMMUTABLE_FL` flag is set or not.

    Raises
    ------
    OSError
        If the underlying ioctl fails, a matching `OSError` will be raised.
    """

    if not isinstance(fd, int) or fd < 0:
        raise ValueError()

    flags = array.array('L', [0])
    fcntl.ioctl(fd, FS_IOC_GETFLAGS, flags, True)
    return bool(flags[0] & FS_IMMUTABLE_FL)


def ioctl_toggle_immutable(fd: int, set_to: bool):
    """Toggle FS_IMMUTABLE_FL

    This toggles the `FS_IMMUTABLE_FL` flag on a specified file. It can both set
    and clear the flag.

    Arguments
    ---------
    fd
        File-descriptor to operate on.
    set_to
        Whether to set the `FS_IMMUTABLE_FL` flag or not.

    Raises
    ------
    OSError
        If the underlying ioctl fails, a matching `OSError` will be raised.
    """

    if not isinstance(fd, int) or fd < 0:
        raise ValueError()

    flags = array.array('L', [0])
    fcntl.ioctl(fd, FS_IOC_GETFLAGS, flags, True)
    if set_to:
        flags[0] |= FS_IMMUTABLE_FL
    else:
        flags[0] &= ~FS_IMMUTABLE_FL
    fcntl.ioctl(fd, FS_IOC_SETFLAGS, flags, False)


def ioctl_blockdev_flushbuf(fd: int):
    """Flush the block device buffer cache

    NB: This function needs the `CAP_SYS_ADMIN` capability.

    Arguments
    ---------
    fd
        File-descriptor of a block device to operate on.

    Raises
    ------
    OSError
        If the underlying ioctl fails, a matching `OSError`
        will be raised.
    """

    if not isinstance(fd, int) or fd < 0:
        raise ValueError(f"Invalid file descriptor: '{fd}'")

    fcntl.ioctl(fd, BLK_IOC_FLSBUF, 0)


class LibCap:
    """Wrapper for libcap (capabilities commands and library) project"""

    cap_value_t = ctypes.c_int
    _lock = threading.Lock()
    _inst = None

    def __init__(self, lib: ctypes.CDLL) -> None:
        self.lib = lib

        # process-wide bounding set
        get_bound = lib.cap_get_bound
        get_bound.argtypes = (self.cap_value_t,)
        get_bound.restype = ctypes.c_int
        get_bound.errcheck = self._check_result  # type: ignore
        self._get_bound = get_bound

        from_name = lib.cap_from_name
        from_name.argtypes = (ctypes.c_char_p, ctypes.POINTER(self.cap_value_t),)
        from_name.restype = ctypes.c_int
        from_name.errcheck = self._check_result  # type: ignore
        self._from_name = from_name

        to_name = lib.cap_to_name
        to_name.argtypes = (ctypes.c_int,)
        to_name.restype = ctypes.POINTER(ctypes.c_char)
        to_name.errcheck = self._check_result  # type: ignore
        self._to_name = to_name

        free = lib.cap_free
        free.argtypes = (ctypes.c_void_p,)
        free.restype = ctypes.c_int
        free.errcheck = self._check_result  # type: ignore
        self._free = free

    @staticmethod
    def _check_result(result, func, args):
        if result is None or (isinstance(result, int) and result == -1):
            err = ctypes.get_errno()
            msg = f"{func.__name__}{args} -> {result}: error ({err}): {os.strerror(err)}"
            raise OSError(err, msg)
        return result

    @staticmethod
    def make():
        path = ctypes.util.find_library("cap")
        if not path:
            return None

        try:
            lib = ctypes.CDLL(path, use_errno=True)
        except (OSError, ImportError):
            return None

        return LibCap(lib)

    @staticmethod
    def last_cap() -> int:
        """Return the int value of the highest valid capability"""
        try:
            with open("/proc/sys/kernel/cap_last_cap", "rb") as f:
                data = f.read()
                return int(data)
        except FileNotFoundError:
            return 0

    @classmethod
    def get_default(cls) -> "LibCap":
        """Return a singleton instance of the library"""
        with cls._lock:
            if cls._inst is None:
                cls._inst = cls.make()
            return cls._inst

    def get_bound(self, capability: int) -> bool:
        """Return the current value of the capability in the thread's bounding set"""
        # cap = self.cap_value_t(capability)
        return self._get_bound(capability) == 1

    def to_name(self, value: int) -> str:
        """Translate from the capability's integer value to the its symbolic name"""
        raw = self._to_name(value)
        val = ctypes.cast(raw, ctypes.c_char_p).value

        if val is None:
            raise RuntimeError("Failed to cast.")

        res = str(val, encoding="utf-8")
        self._free(raw)
        return res.upper()

    def from_name(self, value: str) -> int:
        """Translate from the symbolic name to its integer value"""
        cap = self.cap_value_t()
        self._from_name(value.encode("utf-8"), ctypes.pointer(cap))
        return int(cap.value)


def cap_is_supported(capability: str = "CAP_CHOWN") -> bool:
    """Return whether a given capability is supported by the system"""
    lib = LibCap.get_default()
    if not lib:
        return False

    try:
        value = lib.from_name(capability)
        lib.get_bound(value)
        return True
    except OSError:
        return False


def cap_bound_set() -> set:
    """Return the calling thread's capability bounding set

    If capabilities are not supported this function will return the empty set.
    """
    lib = LibCap.get_default()
    if not lib:
        return set()

    res = set(
        lib.to_name(cap)
        for cap in range(lib.last_cap() + 1)
        if lib.get_bound(cap)
    )

    return res


def cap_mask_to_set(mask: int) -> set:
    lib = LibCap.get_default()
    if not lib:
        return set()

    def bits(n):
        count = 0
        while n:
            if n & 1:
                yield count
            count += 1
            n >>= 1

    res = {
        lib.to_name(cap) for cap in bits(mask)
    }

    return res


def fcntl_flock(fd: int, lock_type: int, wait: bool = False):
    """Perform File-locking Operation

    This function performs a linux file-locking operation on the specified
    file-descriptor. The specific type of lock must be specified by the caller.
    This function does not allow to specify the byte-range of the file to lock.
    Instead, it always applies the lock operations to the entire file.

    For system-level documentation, see the `fcntl(2)` man-page, especially the
    section about `struct flock` and the locking commands.

    This function always uses the open-file-description locks provided by
    modern linux kernels. This means, locks are tied to the
    open-file-description. That is, they are shared between duplicated
    file-descriptors. Furthermore, acquiring a lock while already holding a
    lock will update the lock to the new specified lock type, rather than
    acquiring a new lock.

    If `wait` is `False` a non-blocking operation is performed. In case the lock
    is contested a `BlockingIOError` is raised by the python standard library.
    If `Wait` is `True`, the kernel will suspend execution until the lock is
    acquired.

    If a synchronous exception is raised, the operation will be canceled and the
    exception is forwarded.

    Parameters
    ----------
    fd
        The file-descriptor to use for the locking operation.
    lock_type
        The type of lock to use. This can be one of: `fcntl.F_RDLCK`,
        `fcntl.F_WRLCK`, `fcntl.F_UNLCK`.
    wait
        Whether to suspend execution until the lock is acquired in case of
        contested locks.

    Raises
    ------
    OSError
        If the underlying `fcntl(2)` syscall fails, a matching `OSError` is
        raised. In particular, `BlockingIOError` signals contested locks. The
        POSIX error code is `EAGAIN`.
    """

    valid_types = [fcntl.F_RDLCK, fcntl.F_WRLCK, fcntl.F_UNLCK]
    if lock_type not in valid_types:
        raise ValueError("Unknown lock type")
    if not isinstance(fd, int):
        raise ValueError("File-descriptor is not an integer")
    if fd < 0:
        raise ValueError("File-descriptor is negative")

    #
    # The `OFD` constants are not available through the `fcntl` module, so we
    # need to use their integer representations directly. They are the same
    # across all linux ABIs:
    #
    #     F_OFD_GETLK = 36
    #     F_OFD_SETLK = 37
    #     F_OFD_SETLKW = 38
    #

    if wait:
        lock_cmd = 38
    else:
        lock_cmd = 37

    #
    # We use the linux open-file-descriptor (OFD) version of the POSIX file
    # locking operations. They attach locks to an open file description, rather
    # than to a process. They have clear, useful semantics.
    # This means, we need to use the `fcntl(2)` operation with `struct flock`,
    # which is rather unfortunate, since it varies depending on compiler
    # arguments used for the python library, as well as depends on the host
    # architecture, etc.
    #
    # The structure layout of the locking argument is:
    #
    #     struct flock {
    #         short int l_type;
    #         short int l_whence;
    #         off_t l_start;
    #         off_t l_len;
    #         pid_t int l_pid;
    #     }
    #
    # The possible options for `l_whence` are `SEEK_SET`, `SEEK_CUR`, and
    # `SEEK_END`. All are provided by the `fcntl` module. Same for the possible
    # options for `l_type`, which are `L_RDLCK`, `L_WRLCK`, and `L_UNLCK`.
    #
    # Depending on which architecture you run on, but also depending on whether
    # large-file mode was enabled to compile the python library, the values of
    # the constants as well as the sizes of `off_t` can change. What we know is
    # that `short int` is always 16-bit on linux, and we know that `fcntl(2)`
    # does not take a `size` parameter. Therefore, the kernel will just fetch
    # the structure from user-space with the correct size. The python wrapper
    # `fcntl.fcntl()` always uses a 1024-bytes buffer and thus we can just pad
    # our argument with trailing zeros to provide a valid argument to the
    # kernel. Note that your libc might also do automatic translation to
    # `fcntl64(2)` and `struct flock64` (if you run on 32bit machines with
    # large-file support enabled). Also, random architectures change trailing
    # padding of the structure (MIPS-ABI32 adds 128-byte trailing padding,
    # SPARC adds 16?).
    #
    # To avoid all this mess, we use the fact that we only care for `l_type`.
    # Everything else is always set to 0 in all our needed locking calls.
    # Therefore, we simply use the largest possible `struct flock` for your
    # libc and set everything to 0. The `l_type` field is guaranteed to be
    # 16-bit, so it will have the correct offset, alignment, and endianness
    # without us doing anything. Downside of all this is that all our locks
    # always affect the entire file. However, we do not need locks for specific
    # sub-regions of a file, so we should be fine. Eventually, what we end up
    # with passing to libc is:
    #
    #     struct flock {
    #         uint16_t l_type;
    #         uint16_t l_whence;
    #         uint32_t pad0;
    #         uint64_t pad1;
    #         uint64_t pad2;
    #         uint32_t pad3;
    #         uint32_t pad4;
    #     }
    #

    type_flock64 = struct.Struct('=HHIQQII')
    arg_flock64 = type_flock64.pack(lock_type, 0, 0, 0, 0, 0, 0)

    #
    # Since python-3.5 (PEP475) the standard library guards around `EINTR` and
    # automatically retries the operation. Hence, there is no need to retry
    # waiting calls. If a python signal handler raises an exception, the
    # operation is not retried and the exception is forwarded.
    #

    fcntl.fcntl(fd, lock_cmd, arg_flock64)


class c_timespec(ctypes.Structure):
    _fields_ = [('tv_sec', ctypes.c_long), ('tv_nsec', ctypes.c_long)]


class c_timespec_times2(ctypes.Structure):
    _fields_ = [('atime', c_timespec), ('mtime', c_timespec)]


class Libc:
    """Safe Access to libc

    This class provides selected safe accessors to libc functionality. It is
    highly linux-specific and uses `ctypes.CDLL` to access `libc`.
    """

    AT_FDCWD = ctypes.c_int(-100)
    RENAME_EXCHANGE = ctypes.c_uint(2)
    RENAME_NOREPLACE = ctypes.c_uint(1)
    RENAME_WHITEOUT = ctypes.c_uint(4)

    # see /usr/include/x86_64-linux-gnu/bits/stat.h
    UTIME_NOW = ctypes.c_long(((1 << 30) - 1))
    UTIME_OMIT = ctypes.c_long(((1 << 30) - 2))

    _lock = threading.Lock()
    _inst = None

    def __init__(self, lib: ctypes.CDLL):
        self._lib = lib

        # prototype: renameat2
        proto = ctypes.CFUNCTYPE(
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
            use_errno=True,
        )(
            ("renameat2", self._lib),
            (
                (1, "olddirfd", self.AT_FDCWD),
                (1, "oldpath"),
                (1, "newdirfd", self.AT_FDCWD),
                (1, "newpath"),
                (1, "flags", 0),
            ),
        )
        setattr(proto, "errcheck", self._errcheck_errno)
        setattr(proto, "__name__", "renameat2")
        self.renameat2 = proto
        # prototype: futimens
        proto = ctypes.CFUNCTYPE(
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(c_timespec_times2),
            use_errno=True,
        )(
            ("futimens", self._lib),
            (
                (1, "fd"),
                (1, "timespec"),
            ),
        )
        setattr(proto, "errcheck", self._errcheck_errno)
        setattr(proto, "__name__", "futimens")
        self.futimens = proto

    @staticmethod
    def make() -> "Libc":
        """Create a new instance"""

        return Libc(ctypes.CDLL("", use_errno=True))

    @classmethod
    def default(cls) -> "Libc":
        """Return and possibly create the default singleton instance"""

        with cls._lock:
            if cls._inst is None:
                cls._inst = cls.make()
            return cls._inst

    @staticmethod
    def _errcheck_errno(result, func, args):
        if result < 0:
            err = ctypes.get_errno()
            msg = f"{func.__name__}{args} -> {result}: error ({err}): {os.strerror(err)}"
            raise OSError(err, msg)
        return result


def proc_boot_id(appid: str):
    """Acquire Application-specific Boot-ID

    This queries the kernel for the boot-id of the running system. It then
    calculates an application-specific boot-id by combining the kernel boot-id
    with the provided application-id. This uses a cryptographic HMAC.
    Therefore, the kernel boot-id will not be deducable from the output. This
    allows the caller to use the resulting application specific boot-id for any
    purpose they wish without exposing the confidential kernel boot-id.

    This always returns an object of type `uuid.UUID` from the python standard
    library. Furthermore, this always produces UUIDs of version 4 variant 1.

    Parameters
    ----------
    appid
        An arbitrary object (usually a string) that identifies the use-case of
        the boot-id.
    """

    with open("/proc/sys/kernel/random/boot_id", "r", encoding="utf8") as f:
        content = f.read().strip(" \t\r\n")

    # Running the boot-id through HMAC-SHA256 guarantees that the original
    # boot-id will not be exposed. Thus two IDs generated with this interface
    # will not allow to deduce whether they share a common boot-id.
    # From the result, we throw away everything but the lower 128bits and then
    # turn it into a UUID version 4 variant 1.
    h = bytearray(hmac.new(content.encode(), appid.encode(), hashlib.sha256).digest())  # type: ignore
    h[6] = (h[6] & 0x0f) | 0x40  # mark as version 4
    h[8] = (h[6] & 0x3f) | 0x80  # mark as variant 1
    return uuid.UUID(bytes=bytes(h[0:16]))
