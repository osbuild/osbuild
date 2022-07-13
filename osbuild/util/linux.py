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
import os
import platform
import threading


__all__ = [
    "ioctl_get_immutable",
    "ioctl_toggle_immutable",
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
