import contextlib
import os

from . import api, loop
from .util import jsoncomm

__all__ = [
    "LoopClient",
    "LoopServer"
]


class LoopServer(api.BaseAPI):
    """Server for creating loopback devices

    The server listens for requests on a AF_UNIX/SOCK_DRGAM sockets.

    A request should contain SCM_RIGHTS of two filedescriptors, one
    that sholud be the backing file for the new loopdevice, and a
    second that should be a directory file descriptor where the new
    device node will be created.

    The payload should be a JSON object with the mandatory arguments
    @fd which is the offset in the SCM_RIGHTS array for the backing
    file descriptor and @dir_fd which is the offset for the output
    directory. Optionally, @offset and @sizelimit in bytes may also
    be specified.

    The server respods with a JSON object containing the device name
    of the new device node created in the output directory.

    The created loopback device is guaranteed to be bound to the
    given backing file descriptor for the lifetime of the LoopServer
    object.
    """

    endpoint = "remoteloop"

    def __init__(self, *, socket_address=None):
        super().__init__(socket_address)
        self.devs = []
        self.ctl = None

    def _lazy_init(self):
        if not self.ctl:
            self.ctl = loop.LoopControl()

    def _create_device(
            self,
            fd,
            dir_fd,
            offset=None,
            sizelimit=None,
            lock=False,
            partscan=False,
            read_only=False,
            sector_size=512):
        self._lazy_init()
        lo = self.ctl.loop_for_fd(fd, lock=lock,
                                  offset=offset,
                                  sizelimit=sizelimit,
                                  blocksize=sector_size,
                                  partscan=partscan,
                                  read_only=read_only,
                                  autoclear=True)
        lo.mknod(dir_fd)
        # Pin the Loop objects so they are only released when the LoopServer
        # is destroyed.
        self.devs.append(lo)
        return lo.devname

    def _message(self, msg, fds, sock):
        fd = fds[msg["fd"]]
        dir_fd = fds[msg["dir_fd"]]
        offset = msg.get("offset")
        sizelimit = msg.get("sizelimit")
        lock = msg.get("lock", False)
        partscan = msg.get("partscan", False)
        read_only = msg.get("read_only", False)
        sector_size = msg.get("sector_size", 512)

        devname = self._create_device(fd, dir_fd, offset, sizelimit, lock, partscan, read_only, sector_size)
        sock.send({"devname": devname})

    def _cleanup(self):
        for lo in self.devs:
            lo.close()
        if self.ctl:
            self.ctl.close()


class LoopClient:
    client = None

    def __init__(self, connect_to):
        self.client = jsoncomm.Socket.new_client(connect_to)

    def __del__(self):
        if self.client is not None:
            self.client.close()

    @contextlib.contextmanager
    def device(
            self,
            filename,
            offset=None,
            sizelimit=None,
            lock=False,
            partscan=False,
            read_only=False,
            sector_size=512):
        req = {}
        fds = []

        flags = os.O_RDONLY if read_only else os.O_RDWR
        fd = os.open(filename, flags)
        dir_fd = os.open("/dev", os.O_DIRECTORY)

        fds.append(fd)
        req["fd"] = 0
        fds.append(dir_fd)
        req["dir_fd"] = 1

        if offset:
            req["offset"] = offset
        if sizelimit:
            req["sizelimit"] = sizelimit
        req["lock"] = lock
        req["partscan"] = partscan
        req["read_only"] = read_only
        req["sector_size"] = sector_size

        self.client.send(req, fds=fds)
        os.close(dir_fd)
        os.close(fd)

        msg, _, _ = self.client.recv()
        err = api.get_exception_from_msg(msg)
        if err:
            raise RuntimeError(err)
        path = os.path.join("/dev", msg["devname"])
        try:
            yield path
        finally:
            os.unlink(path)
