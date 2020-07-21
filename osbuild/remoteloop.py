import asyncio
import contextlib
import errno
import os
import threading
from . import loop
from .util import jsoncomm


__all__ = [
    "LoopClient",
    "LoopServer"
]


class LoopServer:
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

    def __init__(self, socket_address):
        self.socket_address = socket_address
        self.devs = []
        self.ctl = loop.LoopControl()
        self.event_loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_event_loop)
        self.barrier = threading.Barrier(2)

    def _create_device(self, fd, dir_fd, offset=None, sizelimit=None):
        while True:
            # Getting an unbound loopback device and attaching a backing
            # file descriptor to it is racy, so we must use a retry loop
            lo = loop.Loop(self.ctl.get_unbound())
            try:
                lo.set_fd(fd)
            except OSError as e:
                lo.close()
                if e.errno == errno.EBUSY:
                    continue
                raise e
            # `set_status` returns EBUSY when the pages from the previously
            # bound file have not been fully cleared yet.
            try:
                lo.set_status(offset=offset, sizelimit=sizelimit, autoclear=True)
            except BlockingIOError:
                lo.clear_fd()
                lo.close()
                continue
            break

        lo.mknod(dir_fd)
        # Pin the Loop objects so they are only released when the LoopServer
        # is destroyed.
        self.devs.append(lo)
        return lo.devname

    def _dispatch(self, server):
        args, fds, addr = server.recv()

        fd = fds[args["fd"]]
        dir_fd = fds[args["dir_fd"]]
        offset = args.get("offset")
        sizelimit = args.get("sizelimit")

        devname = self._create_device(fd, dir_fd, offset, sizelimit)
        server.send({"devname": devname}, destination=addr)
        fds.close()

    def _run_event_loop(self):
        with jsoncomm.Socket.new_server(self.socket_address) as server:
            self.barrier.wait()
            self.event_loop.add_reader(server, self._dispatch, server)
            asyncio.set_event_loop(self.event_loop)
            self.event_loop.run_forever()
            self.event_loop.remove_reader(server)

    def __enter__(self):
        self.thread.start()
        self.barrier.wait()
        return self

    def __exit__(self, *args):
        self.event_loop.call_soon_threadsafe(self.event_loop.stop)
        self.thread.join()
        self.event_loop.close()
        for lo in self.devs:
            lo.close()


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
        try:
            yield path
        finally:
            os.unlink(path)
