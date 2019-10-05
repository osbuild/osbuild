import array
import asyncio
import contextlib
import errno
import json
import os
import socket
import threading
from . import loop


__all__ = [
    "LoopClient",
    "LoopServer"
]


def load_fds(sock, msglen):
    fds = array.array("i")   # Array of ints
    msg, ancdata, _, addr = sock.recvmsg(msglen, socket.CMSG_LEN(253 * fds.itemsize))
    for cmsg_level, cmsg_type, cmsg_data in ancdata:
        if (cmsg_level == socket.SOL_SOCKET and cmsg_type == socket.SCM_RIGHTS):
            # Append data, ignoring any truncated integers at the end.
            fds.fromstring(cmsg_data[:len(cmsg_data) - (len(cmsg_data) % fds.itemsize)])
    return json.loads(msg), list(fds), addr


def dump_fds(sock, obj, fds):
    sock.sendmsg([json.dumps(obj).encode('utf-8')], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds))])


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

    def __init__(self, sock):
        self.devs = []
        self.sock = sock
        self.ctl = loop.LoopControl()
        self.event_loop = asyncio.new_event_loop()
        self.event_loop.add_reader(self.sock, self._dispatch)
        self.thread = threading.Thread(target=self._run_event_loop)

    def __del__(self):
        self.sock.close()

    def _create_device(self, fd, dir_fd, offset=None, sizelimit=None):
        while True:
            # Getting an unbound loopback device and attaching a backing
            # file descriptor to it is racy, so we must use a retry loop
            lo = loop.Loop(self.ctl.get_unbound())
            try:
                lo.set_fd(fd)
            except OSError as e:
                if e.errno == errno.EBUSY:
                    continue
                raise e
            break
        lo.set_status(offset=offset, sizelimit=sizelimit, autoclear=True)
        lo.mknod(dir_fd)
        # Pin the Loop objects so they are only released when the LoopServer
        # is destroyed.
        self.devs.append(lo)
        return lo.devname

    def _dispatch(self):
        args, fds, addr = load_fds(self.sock, 1024)

        fd = fds[args["fd"]]
        dir_fd = fds[args["dir_fd"]]
        offset = args.get("offset")
        sizelimit = args.get("sizelimit")

        devname = self._create_device(fd, dir_fd, offset, sizelimit)
        ret = json.dumps({"devname": devname})
        self.sock.sendto(ret.encode('utf-8'), addr)

    def _run_event_loop(self):
        # Set the thread-local event loop
        asyncio.set_event_loop(self.event_loop)
        # Run event loop until stopped
        self.event_loop.run_forever()

    def __enter__(self):
        self.thread.start()

    def __exit__(self, *args):
        self.event_loop.call_soon_threadsafe(self.event_loop.stop)
        self.thread.join()


class LoopClient:
    def __init__(self, sock):
        self.sock = sock

    @contextlib.contextmanager
    def device(self, filename, offset=None, sizelimit=None):
        req = {}
        fds = array.array("i")
        fd = os.open(filename, os.O_RDWR | os.O_DIRECT)
        dir_fd = os.open("/dev", os.O_DIRECTORY)

        fds.append(fd)
        req["fd"] = 0
        fds.append(dir_fd)
        req["dir_fd"] = 1

        if offset:
            req["offset"] = offset
        if sizelimit:
            req["sizelimit"] = sizelimit

        dump_fds(self.sock, req, fds)
        os.close(dir_fd)
        os.close(fd)

        ret = json.loads(self.sock.recv(1024))
        path = os.path.join("/dev", ret["devname"])
        try:
            yield path
        finally:
            os.unlink(path)
