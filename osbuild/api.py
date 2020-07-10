import asyncio
import io
import json
import os
import tempfile
import threading
from .util import jsoncomm


class API:
    def __init__(self, socket_address, args, monitor):
        self.socket_address = socket_address
        self.input = args
        self._output_data = io.StringIO()
        self._output_pipe = None
        self.monitor = monitor
        self.event_loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_event_loop)
        self.barrier = threading.Barrier(2)

    @property
    def output(self):
        return self._output_data.getvalue()

    def _prepare_input(self):
        with tempfile.TemporaryFile() as fd:
            fd.write(json.dumps(self.input).encode('utf-8'))
            # re-open the file to get a read-only file descriptor
            return open(f"/proc/self/fd/{fd.fileno()}", "r")

    def _prepare_output(self):
        r, w = os.pipe()
        self._output_pipe = r
        self._output_data.truncate(0)
        self._output_data.seek(0)
        self.event_loop.add_reader(r, self._output_ready)
        return os.fdopen(w)

    def _output_ready(self):
        raw = os.read(self._output_pipe, 4096)
        data = raw.decode("utf-8")
        self._output_data.write(data)
        self.monitor.log(data)

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
        msg, _, addr = server.recv()
        if msg["method"] == 'setup-stdio':
            self._setup_stdio(server, addr)

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
        if self._output_pipe:
            os.close(self._output_pipe)
            self._output_pipe = None
