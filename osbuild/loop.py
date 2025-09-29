import contextlib
import ctypes
import errno
import fcntl
import os
import stat
import subprocess
import sys
import time
from typing import Callable, Optional

from .util import linux

__all__ = [
    "Loop",
    "LoopControl",
    "UnexpectedDevice"
]


class UnexpectedDevice(Exception):
    def __init__(self, expected_minor, rdev, mode):
        super().__init__()
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

    @property
    def autoclear(self) -> bool:
        """Return if `LO_FLAGS_AUTOCLEAR` is set in `lo_flags`"""
        return bool(self.lo_flags & Loop.LO_FLAGS_AUTOCLEAR)

    def is_bound_to(self, info: os.stat_result) -> bool:
        """Return if the loop device is bound to the file `info`"""
        return (self.lo_device == info.st_dev and
                self.lo_inode == info.st_ino)


class LoopConfig(ctypes.Structure):
    _fields_ = [
        ('fd', ctypes.c_uint32),
        ('block_size', ctypes.c_uint32),
        ('info', LoopInfo),
        ('__reserved', ctypes.c_uint64 * 8),
    ]


class Loop:
    """Loopback device

    A class representing a Linux loopback device, typically found at
    /dev/loop{minor}.

    Methods
    -------
    loop_configure(fd)
        Bind a file descriptor to the loopback device and set properties of the loopback device
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
    LOOP_CONFIGURE = 0x4C0A

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
        self.on_close = None
        self.fd = -1

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

    def __del__(self):
        self.close()

    def close(self):
        """Close this loop device.

        No operations on this object are valid after this call.
        """
        fd, self.fd = self.fd, -1
        if fd >= 0:
            if callable(self.on_close):
                self.on_close(self)  # pylint: disable=not-callable
            os.close(fd)
            self.devname = "<closed>"

    def flock(self, op: int) -> None:
        """Add or remove an advisory lock on the loopback device

        Perform a lock operation on the loopback device via `flock(2)`.

        The locks are per file-descriptor and thus duplicated fds share
        the same lock. The lock is automatically released when all of
        those duplicated fds are closed or an explicit `LOCK_UN` call
        was made on any of them.

        NB: These locks are advisory only and are not preventing anyone
        from actually accessing the device, but they will prevent udev
        probing the device, see https://systemd.io/BLOCK_DEVICE_LOCKING

        If the file is already locked any attempt to lock it again via
        a different (non-duped) fd will block or, if `fcntl.LOCK_NB`
        is specified, will raise a `BlockingIOError`.

        Parameters
        ----------
        op : int
            the lock operation to perform; one, or a combination, of:
                `fcntl.LOCK_EX`: exclusive lock
                `fcntl.LOCK_SH`: shared lock
                `fcntl.LOCK_NB`: don't block on lock acquisition
                `fcntl.LOCK_UN`: unlock
        """

        fcntl.flock(self.fd, op)

    def flush_buf(self) -> None:
        """Flush the buffer cache of the loopback device

        This function might be required to be called before the usage
        of `clear_fd`. It seems that the kernel (as of version 5.13.8)
        is not clearing the buffer cache of the block device layer in
        case the fd is manually cleared.

        NB: This function needs the `CAP_SYS_ADMIN` capability.
        """

        linux.ioctl_blockdev_flushbuf(self.fd)

    def set_fd(self, fd):
        """
        Deprecated, use configure instead.
        TODO delete this after image-info gets updated.
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

    def clear_fd_wait(self, fd: int, timeout: float, wait: float = 0.1) -> None:
        """Wait until the file descriptor is cleared

        When clearing the file descriptor of the loopback device the
        kernel will check if the loop device has a reference count
        greater then one(!), i.e. if another fd besied the one trying
        to clear the loopback device is open. If so it will only set
        the `LO_FLAGS_AUTOCLEAR` flag and wait until the the device
        is released. This means we cannot be sure the loopback device
        is actually cleared.
        To alleviated this situation we wait until the the loop is not
        bound anymore or not bound to `fd` anymore (in case someone
        else bound it between checks).

        Raises a `TimeoutError` if the file descriptor when `timeout`
        is reached.

        Parameters
        ----------
        fd : int
            the file descriptor to wait for
        timeout : float
            the maximum time to wait in seconds
        wait : float
            the time to wait between each check in seconds
        """

        file_info = os.fstat(fd)
        endtime = time.monotonic() + timeout

        # wait until the loop device is unbound, which means calling
        # `get_status` will fail with `ENXIO` or if someone raced us
        # and bound the loop device again, it is not backed by "our"
        # file descriptor specified via `fd` anymore
        while True:

            try:
                self.clear_fd()
                loop_info = self.get_status()

            except OSError as err:

                # check if the loop is still bound
                if err.errno == errno.ENXIO:
                    return

            # check if it is backed by the fd
            if not loop_info.is_bound_to(file_info):
                return

            if time.monotonic() > endtime:
                raise TimeoutError("waiting for loop device timed out")

            time.sleep(wait)

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

    def is_bound_to(self, fd: int) -> bool:
        """Check if the loopback device is bound to `fd`

        Checks if the loopback device is bound and, if so, whether the
        backing file refers to the same file as `fd`. The latter is
        done by comparing the device and inode information.

        Parameters
        ----------
        fd : int
            the file descriptor to check

        Returns
        -------
        bool
            True if the loopback device is bound to the file descriptor
        """

        try:
            loop_info = self.get_status()
        except OSError as err:

            # raised if the loopback is bound at all
            if err.errno == errno.ENXIO:
                return False

        file_info = os.fstat(fd)

        # it is bound, check if it is bound by `fd`
        return loop_info.is_bound_to(file_info)

    def _config_info(self, info, offset, sizelimit, autoclear, partscan, read_only):
        #  pylint: disable=attribute-defined-outside-init
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
        if read_only is not None:
            if read_only:
                info.lo_flags |= self.LO_FLAGS_READ_ONLY
            else:
                info.lo_flags &= ~self.LO_FLAGS_READ_ONLY
        return info

    def set_status(self, offset=None, sizelimit=None, autoclear=None, partscan=None, read_only=None):
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
        limit of 0 means unlimited.

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
        read_only : bool, optional
            Whether or not to setup the loopback device as read-only (default
            is None).
        """

        info = self._config_info(self.get_status(), offset, sizelimit, autoclear, partscan, read_only)
        fcntl.ioctl(self.fd, self.LOOP_SET_STATUS64, info)

    def configure(self, fd: int, offset=None, sizelimit=None, blocksize=0, autoclear=None, partscan=None,
                  read_only=None):
        """
        Configure the loopback device
        Bind and configure in a single operation a file descriptor to the
        loopback device.
        Only supported for kenel >= 5.8
        Will fall back to set_fd/set_status otherwise.

        The loopback device must be unbound. The backing file must be
        either a regular file or a block device. If the backing file is
        itself a loopback device, then a cycle must not be created. If
        the backing file is opened read-only, then the resulting
        loopback device will be read-only too.

        The properties will be cleared once the device is unbound, but preserved
        by changing the backing file descriptor.

        Note that this operation is not atomic: All the current properties
        are read out, the ones specified in this function call are modified,
        and then they are written back. For this reason, concurrent
        modification of the properties must be avoided.

        Setting sizelimit means the size of the loopback device is taken
        to be the max of the size of the backing file and the limit. A
        limit of 0 means unlimited.

        Enabling autoclear has the same effect as calling clear_fd().

        When partscan is first enabled, the partition table of the
        device is scanned, and new blockdevices potentially added for
        the partitions.

        Parameters
        ----------
        fd : int
            the file descriptor to bind
        offset : int, optional
            The offset in bytes from the start of the backing file, or
            None to leave unchanged (default is None)
        sizelimit : int, optional
            The max size in bytes to make the loopback device, or None
            to leave unchanged (default is None)
        blocksize : int, optional
            Set the logical blocksize of the loopback device. Default is 0.
        autoclear : bool, optional
            Whether or not to enable autoclear, or None to leave unchanged
            (default is None)
        partscan : bool, optional
            Whether or not to enable partition scanning, or None to leave
            unchanged (default is None)
        read_only : bool, optional
            Whether or not to setup the loopback device as read-only (default
            is None).
        """
        #  pylint: disable=attribute-defined-outside-init
        config = LoopConfig()
        config.fd = fd
        config.block_size = int(blocksize)
        config.info = self._config_info(LoopInfo(), offset, sizelimit, autoclear, partscan, read_only)
        try:
            fcntl.ioctl(self.fd, self.LOOP_CONFIGURE, config)
        except OSError as e:
            if e.errno != errno.EINVAL:
                raise
            fcntl.ioctl(self.fd, self.LOOP_SET_FD, config.fd)
            fcntl.ioctl(self.fd, self.LOOP_SET_STATUS64, config.info)

    def get_status(self) -> LoopInfo:
        """Get properties of the loopback device

        Return a `LoopInfo` structure with the information of this
        loopback device. See loop(4) for more information.
        """

        info = LoopInfo()
        fcntl.ioctl(self.fd, self.LOOP_GET_STATUS64, info)
        return info

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

    def mknod(self, dir_fd, mode=0o600):
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

        If the host device is available, then it will be bind-mounted
        in place, otherwise a new node will be created.

        Parameters
        ----------
        dir_fd : int
            Target directory file descriptor
        mode : int, optional
            Access mode on the created device node (0o600 is default)
        """

        host_path = f"/dev/{self.devname}"
        # if we have the host_path, try to bind mount it into the dir_fd as this is less privileged
        # than mknod(), if that works just return. If it fails (e.g. because of kernel mount namespace
        # issues) fallback to mknod to avoid regressions
        if os.path.exists(host_path):
            os.mknod(self.devname, mode=(stat.S_IMODE(mode)),
                     dir_fd=dir_fd)
            try:
                subprocess.run(["mount", "--bind", host_path, self.devname], cwd=f"/proc/self/fd/{dir_fd}/", check=True)
                return
            except subprocess.CalledProcessError as e:
                print(f"WARNING: {e}: {e.stderr}", file=sys.stderr)
                # bind mount will fail if we try it accross bind mount
                # boundaries
                os.unlink(self.devname, dir_fd=dir_fd)
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

        with contextlib.ExitStack() as stack:
            if not dir_fd:
                dir_fd = os.open("/dev", os.O_DIRECTORY)
                stack.callback(lambda: os.close(dir_fd))

            self.fd = os.open("loop-control", os.O_RDWR, dir_fd=dir_fd)

    def __del__(self):
        self.close()

    def _check_open(self):
        if self.fd < 0:
            raise RuntimeError("LoopControl closed")

    def close(self):
        """Close the loop control file-descriptor

        No operations on this object are valid after this call,
        with the exception of this `close` method which then
        is a no-op.
        """
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

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

        self._check_open()
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

        self._check_open()
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

        self._check_open()
        return fcntl.ioctl(self.fd, self.LOOP_CTL_GET_FREE)

    def loop_for_fd(self,
                    fd: int,
                    lock: bool = False,
                    setup: Optional[Callable[[Loop], None]] = None,
                    **kwargs):
        """
        Get or create an unbound loopback device and bind it to an fd

        Getting an unbound loopback device, attaching a backing file
        descriptor and setting the loop device status is racy so this
        method will retry until it succeeds or it fails to get an
        unbound loop device.

        If `lock` is set, an exclusive advisory lock will be taken
        on the device before the device gets configured. If this
        fails, the next loop device will be tried.
        Locking the device can be helpful to prevent systemd-udevd from
        reacting to changes to the device, like processing udev rules.
        See https://systemd.io/BLOCK_DEVICE_LOCKING/

        A callback can be specified via `setup` that will be invoked
        after the loop device is opened but before any other operation
        is done, such as setting the backing file.

        All given keyword arguments except `lock` are forwarded to the
        `Loop.set_status` call.
        """

        self._check_open()

        if fd < 0:
            raise ValueError(f"Invalid file descriptor '{fd}'")

        while True:
            lo = Loop(self.get_unbound())

            # if a setup callback is specified invoke it now
            if callable(setup):
                try:
                    setup(lo)
                except BaseException:
                    lo.close()
                    raise

            # try to lock the device if requested and use a
            # different one if it fails
            if lock:
                try:
                    lo.flock(fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    lo.close()
                    continue

            try:
                lo.configure(fd, **kwargs)
            except BlockingIOError:
                lo.clear_fd()
                lo.close()
                continue
            except OSError as e:
                lo.close()
                # `loop_configure` returns EBUSY when the pages from the
                # previously bound file have not been fully cleared yet.
                if e.errno == errno.EBUSY:
                    continue
                raise e
            break

        return lo
