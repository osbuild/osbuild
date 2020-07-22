import abc
import asyncio
import io
import json
import os
import sys
import tempfile
import threading
from .util import jsoncomm


__all__ = [
    "API"
]


class BaseAPI(abc.ABC):
    """Base class for all API providers

    This base class provides the basic scaffolding for setting
    up API endpoints, normally to be used for bi-directional
    communication from and to the sandbox. It is to be used as
    a context manger. The communication channel will only be
    established on entering the context and will be shut down
    when the context is left.

    The `_dispatch` method needs to be implemented by child
    classes, and is called for incoming messages.
    Optionally, the `_cleanup` method can be implemented, to
    clean up resources after the context is left and the
    communication channel shut down.
    """
    def __init__(self, socket_address):
        self.socket_address = socket_address
        self.barrier = threading.Barrier(2)
        self.event_loop = None
        self.thread = None

    @abc.abstractmethod
    def _dispatch(self, server):
        """Called for incoming messages on the socket"""

    def _cleanup(self):
        """Called after the event loop is shut down"""

    def _run_event_loop(self):
        with jsoncomm.Socket.new_server(self.socket_address) as server:
            self.barrier.wait()
            self.event_loop.add_reader(server, self._dispatch, server)
            asyncio.set_event_loop(self.event_loop)
            self.event_loop.run_forever()
            self.event_loop.remove_reader(server)

    def __enter__(self):
        # We are not re-entrant, so complain if re-entered.
        assert self.event_loop is None

        self.event_loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_event_loop)

        self.barrier.reset()
        self.thread.start()
        self.barrier.wait()

        return self

    def __exit__(self, *args):
        self.event_loop.call_soon_threadsafe(self.event_loop.stop)
        self.thread.join()
        self.event_loop.close()

        # Give deriving classes a chance to clean themselves up
        self._cleanup()

        self.thread = None
        self.event_loop = None


class API(BaseAPI):
    """The main OSBuild API"""
    def __init__(self, socket_address, args, monitor):
        super().__init__(socket_address)
        self.input = args
        self._output_data = io.StringIO()
        self._output_pipe = None
        self.monitor = monitor

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

    def _cleanup(self):
        if self._output_pipe:
            os.close(self._output_pipe)
            self._output_pipe = None


def setup_stdio(path="/run/osbuild/api/osbuild"):
    """Replace standard i/o with the ones provided by the API"""
    with jsoncomm.Socket.new_client(path) as client:
        req = {"method": "setup-stdio"}
        client.send(req)
        msg, fds, _ = client.recv()
        for sio in ["stdin", "stdout", "stderr"]:
            target = getattr(sys, sio)
            source = fds[msg[sio]]
            os.dup2(source, target.fileno())
        fds.close()
