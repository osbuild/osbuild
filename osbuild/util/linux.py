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
import fcntl


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
