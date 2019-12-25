import array
import asyncio
import json
import os
import socket
import sys
import tempfile
import threading


from . import remoteloop


class API:
    def __init__(self, socket_address, args, interactive):
        self.socket_address = socket_address
        self.input = args
        self.interactive = interactive
        self._output = None
        self.event_loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_event_loop)

    @property
    def output(self):
        return self._output and self._output.read()

    def _prepare_input(self):
        with tempfile.TemporaryFile() as fd:
            fd.write(json.dumps(self.input).encode('utf-8'))
            # re-open the file to get a read-only file descriptor
            return open(f"/proc/self/fd/{fd.fileno()}", "r")

    def _prepare_output(self):
        if self.interactive:
            return os.fdopen(os.dup(sys.stdout.fileno()), 'w')
        out = tempfile.TemporaryFile(mode="wb")
        fd = os.open(f"/proc/self/fd/{out.fileno()}", os.O_RDONLY|os.O_CLOEXEC)
        self._output = os.fdopen(fd)
        return out

    def _setup_stdio(self, sock, addr):
        with self._prepare_input() as stdin, \
             self._prepare_output() as stdout:
            msg = {}
            fds = array.array("i")
            fds.append(stdin.fileno())
            msg['stdin'] = 0
            fds.append(stdout.fileno())
            msg['stdout'] = 1
            fds.append(stdout.fileno())
            msg['stderr'] = 2
            remoteloop.dump_fds(sock, msg, fds, addr=addr)

    def _dispatch(self, sock):
        msg, addr = sock.recvfrom(1024)
        args = json.loads(msg)
        if args["method"] == 'setup-stdio':
            self._setup_stdio(sock, addr)

    def _run_event_loop(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.bind(self.socket_address)
        self.event_loop.add_reader(sock, self._dispatch, sock)
        asyncio.set_event_loop(self.event_loop)
        self.event_loop.run_forever()
        self.event_loop.remove_reader(sock)
        sock.close()

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.event_loop.call_soon_threadsafe(self.event_loop.stop)
        self.thread.join()
