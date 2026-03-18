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

    def __init__(self, rundir, devdir="/dev"):
        super().__init__(rundir)
        self.devdir = devdir
        self.devices = {}
        self.ctl = None

    def _lazy_init(self):
        if not self.ctl:
            self.ctl = loop.LoopControl()

    def _create(self, msg, fds, sock):
        self._lazy_init()
        lo = self.ctl.loop_for_fd(fds[msg["fd"]],
                                  lock=msg.get("lock", False),
                                  offset=msg.get("offset"),
                                  sizelimit=msg.get("sizelimit"),
                                  blocksize=msg.get("sector_size", 512),
                                  partscan=msg.get("partscan", False),
                                  read_only=msg.get("read_only", False),
                                  autoclear=True)

        dir_fd = os.open(self.devdir, os.O_DIRECTORY)
        lo.mknod(dir_fd)
        os.close(dir_fd)

        # Pin the Loop objects until the LoopClient closes them or the
        # LoopServer is destroyed
        self.devices[lo.devname] = lo
        return { "devname": lo.devname }

    def _close(self, msg, fds, sock):
        self.devices.pop(msg["devname"]).close()
        return {}

    def _message(self, msg, fds, sock):
        if msg["method"] == "create":
            sock.send(self._create(msg, fds, sock))
        elif msg["method"] == "close":
            sock.send(self._close(msg, fds, sock))

    def _cleanup(self):
        for lo in self.devices.values():
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
        flags = os.O_RDONLY if read_only else os.O_RDWR
        fd = os.open(filename, flags)

        req = {
            "method": "create",
            "fd": 0,
            "lock": lock,
            "partscan": partscan,
            "read_only": read_only,
            "sector_size": sector_size
        }

        if offset:
            req["offset"] = offset
        if sizelimit:
            req["sizelimit"] = sizelimit

        self.client.send(req, fds=[fd])
        os.close(fd)

        msg, _, _ = self.client.recv()
        err = api.get_exception_from_msg(msg)
        if err:
            raise RuntimeError(err)
        devname = msg["devname"]
        path = os.path.join("/run/osbuild/devices", devname)
        try:
            yield path
        finally:
            self.client.send({ "method": "close", "devname": devname })
            _, _, _ = self.client.recv()
            os.unlink(path)
