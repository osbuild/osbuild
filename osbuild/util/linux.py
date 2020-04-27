"""Linux API Access

This module provides access to linux system-calls and other APIs, in particular
those not provided by the python standard library. The idea is to provide
universal wrappers with broad access to linux APIs. Convenience helpers and
higher-level abstractions are beyond the scope of this module.

In some cases it is overly complex to provide universal access to a specifc
API. Hence, the API might be restricted to a reduced subset of its
functionality, just to make sure we can actually implement the wrappers in a
reasonable manner.
"""


import array
import fcntl
import hashlib
import hmac
import struct
import uuid


__all__ = [
    "fcntl_flock",
    "ioctl_get_immutable",
    "ioctl_toggle_immutable",
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


def fcntl_flock(fd: int, lock_type: int):
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

    So far, this function always performs try-lock operations. The blocking
    mode is currently not exposed.

    Parameters
    ----------
    fd
        The file-descriptor to use for the locking operation.
    lock_type
        The type of lock to use. This can be one of: `fcntl.F_RDLCK`,
        `fcntl.F_WRLCK`, `fcntl.F_UNLCK`.

    Raises
    ------
    OSError
        If the underlying `fcntl(2)` syscall fails, a matching `OSError` is
        raised.
    """

    valid_types = [fcntl.F_RDLCK, fcntl.F_WRLCK, fcntl.F_UNLCK]
    if not isinstance(fd, int) or fd < 0 or not any(lock_type == v for v in valid_types):
        raise ValueError()

    #
    # The `OFD` constants are not available through the `fcntl` module, so we
    # need to use their integer representations directly. They are the same
    # across all linux ABIs:
    #
    #     F_OFD_GETLK = 36
    #     F_OFD_SETLK = 37
    #     F_OFD_SETLKW = 38
    #

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

    fcntl.fcntl(fd, lock_cmd, arg_flock64)


def proc_boot_id(appid):
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

    with open("/proc/sys/kernel/random/boot_id", "r") as f:
        content = f.read().strip(" \t\r\n")

    # Running the boot-id through HMAC-SHA256 guarantees that the original
    # boot-id will not be exposed. Thus two IDs generated with this interface
    # will not allow to deduce whether they share a common boot-id.
    # From the result, we throw away everything but the lower 128bits and then
    # turn it into a UUID version 4 variant 1.
    h = bytearray(hmac.digest(content.encode(), appid.encode(), hashlib.sha256))
    h[6] = (h[6] & 0x0f) | 0x40 # mark as version 4
    h[8] = (h[6] & 0x3f) | 0x80 # mark as variant 1
    return uuid.UUID(bytes=bytes(h[0:16]))
