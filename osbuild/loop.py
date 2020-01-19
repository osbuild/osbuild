import contextlib
import ctypes
import fcntl
import os
import stat


__all__ = [
    "Loop",
    "LoopControl",
    "UnexpectedDevice"
]


class UnexpectedDevice(Exception):
    def __init__(self, expected_minor, rdev, mode):
        super(UnexpectedDevice, self).__init__()
        self.expected_minor = expected_minor
        self.rdev = rdev
        self.mode = mode


class LoopInfo(ctypes.Structure):
    _fields_ = [
        ('lo_device', ctypes.c_uint64),
        ('lo_inode', ctypes.c_uint64),
        ('lo_rdevice', ctypes.c_uint64),
        ('lo_offset', ctypes.c_uint64),
        ('lo_sizelimit', ctypes.c_uint64),
        ('lo_number', ctypes.c_uint32),
        ('lo_encrypt_type', ctypes.c_uint32),
        ('lo_encrypt_key_size', ctypes.c_uint32),
        ('lo_flags', ctypes.c_uint32),
        ('lo_file_name', ctypes.c_uint8 * 64),
        ('lo_crypt_name', ctypes.c_uint8 * 64),
        ('lo_encrypt_key', ctypes.c_uint8 * 32),
        ('lo_init', ctypes.c_uint64 * 2)
    ]


class Loop:
    """Loopback device

    A class representing a Linux loopback device, typically found at
    /dev/loop{minor}.

    Methods
    -------
    set_fd(fd)
        Bind a file descriptor to the loopback device
    clear_fd()
        Unbind the file descriptor from the loopback device
    change_fd(fd)
        Replace the bound file descriptor
    set_capacity()
        Re-read the capacity of the backing file
    set_status(offset=None, sizelimit=None, autoclear=None, partscan=None)
        Set properties of the loopback device
    mknod(dir_fd, mode=0o600)
        Create a secondary device node
    """

    LOOP_MAJOR = 7

    LO_FLAGS_READ_ONLY = 1
    LO_FLAGS_AUTOCLEAR = 4
    LO_FLAGS_PARTSCAN = 8
    LO_FLAGS_DIRECT_IO = 16

    LOOP_SET_FD = 0x4C00
    LOOP_CLR_FD = 0x4C01
    LOOP_SET_STATUS64 = 0x4C04
    LOOP_GET_STATUS64 = 0x4C05
    LOOP_CHANGE_FD = 0x4C06
    LOOP_SET_CAPACITY = 0x4C07
    LOOP_SET_DIRECT_IO = 0x4C08
    LOOP_SET_BLOCK_SIZE = 0x4C09

    def __init__(self, minor, dir_fd=None):
        """
        Parameters
        ----------
        minor
            the minor number of the underlying device
        dir_fd : int, optional
            A directory file descriptor to a filesystem containing the
            underlying device node, or None to use /dev (default is None)

        Raises
        ------
        UnexpectedDevice
            If the file in the expected device node location is not the
            expected device node
        """

        self.devname = f"loop{minor}"
        self.minor = minor

        with contextlib.ExitStack() as stack:
            if not dir_fd:
                dir_fd = os.open("/dev", os.O_DIRECTORY)
                stack.callback(lambda: os.close(dir_fd))
            self.fd = os.open(self.devname, os.O_RDWR, dir_fd=dir_fd)

        info = os.stat(self.fd)
        if ((not stat.S_ISBLK(info.st_mode)) or
                (not os.major(info.st_rdev) == self.LOOP_MAJOR) or
                (not os.minor(info.st_rdev) == minor)):
            raise UnexpectedDevice(minor, info.st_rdev, info.st_mode)

    def set_fd(self, fd):
        """Bind a file descriptor to the loopback device

        The loopback device must be unbound. The backing file must be
        either a regular file or a block device. If the backing file is
        itself a loopback device, then a cycle must not be created. If
        the backing file is opened read-only, then the resulting
        loopback device will be read-only too.

        Parameters
        ----------
        fd : int
            the file descriptor to bind
        """

        fcntl.ioctl(self.fd, self.LOOP_SET_FD, fd)

    def clear_fd(self):
        """Unbind the file descriptor from the loopback device

        The loopback device must be bound. The device is then marked
        to be cleared, so once nobody holds it open any longer the
        backing file is unbound and the device returns to the unbound
        state.
        """

        fcntl.ioctl(self.fd, self.LOOP_CLR_FD)

    def change_fd(self, fd):
        """Replace the bound filedescriptor

        Atomically replace the backing filedescriptor of the loopback
        device, even if the device is held open.

        The effective size (taking sizelimit into account) of the new
        and existing backing file descriptors must be the same, and
        the loopback device must be read-only. The loopback device will
        remain read-only, even if the new file descriptor was opened
        read-write.

        Parameters
        ----------
        fd : int
            the file descriptor to change to
        """

        fcntl.ioctl(self.fd, self.LOOP_CHANGE_FD, fd)

    def set_status(self, offset=None, sizelimit=None, autoclear=None, partscan=None):
        """Set properties of the loopback device

        The loopback device must be bound, and the properties will be
        cleared once the device is unbound, but preserved by changing
        the backing file descriptor.

        Note that this operation is not atomic: All the current properties
        are read out, the ones specified in this function call are modified,
        and then they are written back. For this reason, concurrent
        modification of the properties must be avoided.

        Setting sizelimit means the size of the loopback device is taken
        to be the max of the size of the backing file and the limit. A
        limit of 0 is taken to mean unlimited.

        Enabling autoclear has the same effect as calling clear_fd().

        When partscan is first enabled, the partition table of the
        device is scanned, and new blockdevices potentially added for
        the partitions.

        Parameters
        ----------
        offset : int, optional
            The offset in bytes from the start of the backing file, or
            None to leave unchanged (default is None)
        sizelimit : int, optional
            The max size in bytes to make the loopback device, or None
            to leave unchanged (default is None)
        autoclear : bool, optional
            Whether or not to enable autoclear, or None to leave unchanged
            (default is None)
        partscan : bool, optional
            Whether or not to enable partition scanning, or None to leave
            unchanged (default is None)
        """

        info = LoopInfo()
        fcntl.ioctl(self.fd, self.LOOP_GET_STATUS64, info)
        if offset:
            info.lo_offset = offset
        if sizelimit:
            info.lo_sizelimit = sizelimit
        if autoclear is not None:
            if autoclear:
                info.lo_flags |= self.LO_FLAGS_AUTOCLEAR
            else:
                info.lo_flags &= ~self.LO_FLAGS_AUTOCLEAR
        if partscan is not None:
            if partscan:
                info.lo_flags |= self.LO_FLAGS_PARTSCAN
            else:
                info.lo_flags &= ~self.LO_FLAGS_PARTSCAN
        fcntl.ioctl(self.fd, self.LOOP_SET_STATUS64, info)

    def set_direct_io(self, dio=True):
        """Set the direct-IO property on the loopback device

        Enabling direct IO allows one to avoid double caching, which
        should improve performance and memory usage.

        Parameters
        ----------
        dio : bool, optional
            Whether or not to enable direct IO (default is True)
        """

        fcntl.ioctl(self.fd, self.LOOP_SET_DIRECT_IO, dio)

    def mknod(self, dir_fd=None, mode=0o600):
        """Create a secondary device node

        Create a device node with the correct name, mode, minor and major
        number in the provided directory.

        Note that the device node will survive even if a device is
        unbound and rebound, so anyone with access to the device node
        will have access to any future devices with the same minor
        number. The intended use of this is to first bind a file
        descriptor to a loopback device, then mknod it where it should
        be accessed from, and only after the destination directory is
        ensured to have been destroyed/made inaccessible should the the
        loopback device be unbound.

        Note that the provided directory should not be devtmpfs, as the
        device node is guaranteed to already exist there, and the call
        would hence fail.

        Parameters
        ----------
        dir_fd : int, optional
            Target directory file descriptor, or None to use /dev (None is default)
        mode : int, optional
            Access mode on the created device node (0o600 is default)
        """

        if not dir_fd:
            dir_fd = os.open("/dev", os.O_DIRECTORY)
        os.mknod(self.devname,
                 mode=(stat.S_IMODE(mode) | stat.S_IFBLK),
                 device=os.makedev(self.LOOP_MAJOR, self.minor),
                 dir_fd=dir_fd)


class LoopControl:
    """Loopback control device

    A class representing the Linux loopback control device, typically
    found at /dev/loop-control. It allows the creation and destruction
    of loopback devices.

    A loopback device may be bound, which means that a file descriptor
    has been attached to it as its backing file. Otherwise, it is
    considered unbound.

    Methods
    -------
    add(minor)
        Add a new loopback device
    remove(minor)
        Remove an existing loopback device
    get_unbound()
        Get or create the first unbound loopback device
    """

    LOOP_CTL_ADD = 0x4C80
    LOOP_CTL_REMOVE = 0x4C81
    LOOP_CTL_GET_FREE = 0x4C82

    def __init__(self, dir_fd=None):
        """
        Parameters
        ----------
        dir_fd : int, optional
            A directory filedescriptor to a devtmpfs filesystem,
            or None to use /dev (default is None)
        """

        if not dir_fd:
            dir_fd = os.open("/dev", os.O_DIRECTORY)
        self.fd = os.open("loop-control", os.O_RDWR, dir_fd=dir_fd)

    def add(self, minor=-1):
        """Add a new loopback device

        Add a new, unbound loopback device. If a minor number is given
        and it is positive, a loopback device with that minor number
        is added. Otherwise, if there are no unbound devices, a device
        using the first unused minor number is created.

        Parameters
        ----------
        minor : int, optional
            The requested minor number, or a negative value for
            unspecified (default is -1)

        Returns
        -------
        int
            The minor number of the created device
        """

        return fcntl.ioctl(self.fd, self.LOOP_CTL_ADD, minor)

    def remove(self, minor=-1):
        """Remove an existing loopback device

        Removes an unbound and unopen loopback device. If a minor
        number is given and it is positive, the loopback device
        with that minor number is removed. Otherwise, the first
        unbound device is attempted removed.

        Parameters
        ----------
        minor : int, optional
            The requested minor number, or a negative value for
            unspecified (default is -1)
        """

        fcntl.ioctl(self.fd, self.LOOP_CTL_REMOVE, minor)

    def get_unbound(self):
        """Get or create an unbound loopback device

        If an unbound loopback device exists, returns it.
        Otherwise, create a new one.

        Returns
        -------
        int
            The minor number of the returned device
        """

        return fcntl.ioctl(self.fd, self.LOOP_CTL_GET_FREE)
