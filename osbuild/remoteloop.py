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
        self.ctl = loop.LoopControl()

    def _create_device(self, fd, dir_fd, offset=None, sizelimit=None):
        lo = self.ctl.loop_for_fd(fd, offset=offset, sizelimit=sizelimit, autoclear=True)
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

        devname = self._create_device(fd, dir_fd, offset, sizelimit)
        sock.send({"devname": devname})

    def _cleanup(self):
        for lo in self.devs:
            lo.close()
        self.ctl.close()


class LoopClient:
    client = None

    def __init__(self, connect_to):
        self.client = jsoncomm.Socket.new_client(connect_to)

    def __del__(self):
        if self.client is not None:
            self.client.close()

    @contextlib.contextmanager
    def device(self, filename, offset=None, sizelimit=None):
        req = {}
        fds = []

        fd = os.open(filename, os.O_RDWR)
        dir_fd = os.open("/dev", os.O_DIRECTORY)

        fds.append(fd)
        req["fd"] = 0
        fds.append(dir_fd)
        req["dir_fd"] = 1

        if offset:
            req["offset"] = offset
        if sizelimit:
            req["sizelimit"] = sizelimit

        self.client.send(req, fds=fds)
        os.close(dir_fd)
        os.close(fd)

        payload, _, _ = self.client.recv()
        path = os.path.join("/dev", payload["devname"])
        # debug
        print(f"removeloop.py::device({filename}): fd={fd} dir_fd={dir_fd}")
        print(f" -> path {path}")
        try:
            yield path
        finally:
            os.unlink(path)
