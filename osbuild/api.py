import abc
import asyncio
import contextlib
import io
import json
import os
import sys
import tempfile
import traceback
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
    a context manager. The communication channel will only be
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

    @property
    def running(self):
        return self.event_loop is not None

    def __enter__(self):
        # We are not re-entrant, so complain if re-entered.
        assert not self.running

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
        self.metadata = {}
        self.exception = None

    @property
    def output(self):
        # Only once the event-loop was stopped, you are guaranteed that the
        # api-thread scheduled all outstanding events. Therefore, we disallow
        # asking for the output-data from a running api context. If we happen
        # to need live streaming access to the output in the future, we need
        # to redesign the output-handling, anyway.
        assert not self.running

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

    def _set_metadata(self, message):
        self.metadata.update(message["metadata"])

    def _get_arguments(self, sock):
        with self._prepare_input() as data:
            fds = []
            fds.append(data.fileno())
            sock.send({"type": "fd", "fd": 0}, fds=fds)

    def _get_exception(self, message):
        self.exception = message["exception"]

    def _message(self, msg, fds, sock):
        if msg["method"] == 'add-metadata':
            self._set_metadata(msg)
        elif msg["method"] == 'exception':
            self._get_exception(msg)
        elif msg["method"] == 'get-arguments':
            self._get_arguments(sock)

    def _cleanup(self):
        if self._output_pipe:
            os.close(self._output_pipe)
            self._output_pipe = None

def exception(e, path="/run/osbuild/api/osbuild"):
    """Send exception to osbuild"""
    traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
    with jsoncomm.Socket.new_client(path) as client:
        msg = {
            "method": "exception",
            "exception": {
                "type": str(type(e)),
                "value": str(e),
                "traceback": str(e.__traceback__)
            }
        }
        client.send(msg)

    sys.exit(2)

# pylint: disable=broad-except
@contextlib.contextmanager
def exception_handler(path="/run/osbuild/api/osbuild"):
    try:
        yield
    except Exception as e:
        exception(e, path)

def arguments(path="/run/osbuild/api/osbuild"):
    """Retrieve the input arguments that were supplied to API"""
    with jsoncomm.Socket.new_client(path) as client:
        req = {"method": "get-arguments"}
        client.send(req)
        msg, fds, _ = client.recv()
        assert msg["type"] == "fd"
        fd = msg["fd"]
        with os.fdopen(fds.steal(fd), encoding="utf-8") as f:
            data = json.load(f)
        return data


def metadata(data: Dict, path="/run/osbuild/api/osbuild"):
    """Update metadata for the current module"""
    with jsoncomm.Socket.new_client(path) as client:
        msg = {
            "method": "add-metadata",
            "metadata": data
        }
        client.send(msg)
