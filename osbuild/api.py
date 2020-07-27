import abc
import asyncio
import io
import json
import os
import sys
import tempfile
import threading
from typing import Dict, Optional
from .util.types import PathLike
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

    New messages are delivered via the `_message` method, that
    needs to be implemented by deriving classes.

    Optionally, the `_cleanup` method can be implemented, to
    clean up resources after the context is left and the
    communication channel shut down.

    On incoming messages, first the `_dispatch` method will be
    called; the default implementation will receive the message
    call `_message.`
    """
    def __init__(self, socket_address: Optional[PathLike] = None):
        self.socket_address = socket_address
        self.barrier = threading.Barrier(2)
        self.event_loop = None
        self.thread = None
        self._socketdir = None

    @property
    @classmethod
    @abc.abstractmethod
    def endpoint(cls):
        """The name of the API endpoint"""

    @abc.abstractmethod
    def _message(self, msg: Dict, fds: jsoncomm.FdSet, sock: jsoncomm.Socket):
        """Called for a new incoming message

        The file descriptor set `fds` will be closed after the call.
        Use the `FdSet.steal()` method to extract file descriptors.
        """

    def _cleanup(self):
        """Called after the event loop is shut down"""

    @classmethod
    def _make_socket_dir(cls):
        """Called to create the temporary socket dir"""
        return tempfile.TemporaryDirectory(prefix="api-", dir="/run/osbuild")

    def _dispatch(self, sock: jsoncomm.Socket):
        """Called when data is available on the socket"""
        msg, fds, _ = sock.recv()
        if msg is None:
            # Peer closed the connection
            self.event_loop.remove_reader(sock)
            return
        self._message(msg, fds, sock)
        fds.close()

    def _accept(self, server):
        client = server.accept()
        if client:
            self.event_loop.add_reader(client, self._dispatch, client)

    def _run_event_loop(self):
        with jsoncomm.Socket.new_server(self.socket_address) as server:
            server.blocking = False
            server.listen()
            self.barrier.wait()
            self.event_loop.add_reader(server, self._accept, server)
            asyncio.set_event_loop(self.event_loop)
            self.event_loop.run_forever()
            self.event_loop.remove_reader(server)

    def __enter__(self):
        # We are not re-entrant, so complain if re-entered.
        assert self.event_loop is None

        if not self.socket_address:
            self._socketdir = self._make_socket_dir()
            address = os.path.join(self._socketdir.name, self.endpoint)
            self.socket_address = address

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

        if self._socketdir:
            self._socketdir.cleanup()
            self._socketdir = None
            self.socket_address = None


class API(BaseAPI):
    """The main OSBuild API"""

    endpoint = "osbuild"

    def __init__(self, args, monitor, *, socket_address=None):
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

    def _setup_stdio(self, server):
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

            server.send(msg, fds=fds)

    def _message(self, msg, fds, sock):
        if msg["method"] == 'setup-stdio':
            self._setup_stdio(sock)

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
