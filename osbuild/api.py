import asyncio
import json
import os
import sys
import tempfile
import threading

import osbuild.util.jsoncomm as jsoncomm


class API:
    def __init__(self, socket_address, args, interactive):
        self.socket_address = socket_address
        self.input = args
        self.interactive = interactive
        self._output = None
        self.event_loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_event_loop)
        self.barrier = threading.Barrier(2)

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

    def _setup_stdio(self, server, addr):
        with self._prepare_input() as stdin, \
             self._prepare_output() as stdout:
            msg = {}
            fds = []
            fds.append(stdin.fileno())
            msg['stdin'] = 0
            fds.append(stdout.fileno())
            msg['stdout'] = 1
            fds.append(stdout.fileno())
            msg['stderr'] = 2

            server.send(msg, fds=fds, destination=addr)

    def _dispatch(self, server):
        msg = server.recv()
        if msg[0]["method"] == 'setup-stdio':
            self._setup_stdio(server, msg[2])

    def _run_event_loop(self):
        server = jsoncomm.Socket.new_server(self.socket_address)
        self.barrier.wait()
        self.event_loop.add_reader(server, self._dispatch, server)
        asyncio.set_event_loop(self.event_loop)
        self.event_loop.run_forever()
        self.event_loop.remove_reader(server)
        server.close()

    def __enter__(self):
        self.thread.start()
        self.barrier.wait()
        return self

    def __exit__(self, *args):
        self.event_loop.call_soon_threadsafe(self.event_loop.stop)
        self.thread.join()
