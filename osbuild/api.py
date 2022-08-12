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
from typing import Dict, Optional, Any, IO, Iterator, List, Type
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

    event_loop: Optional[asyncio.AbstractEventLoop] = None
    thread: Optional[threading.Thread] = None
    _socketdir: Optional[tempfile.TemporaryDirectory[Any]] = None

    def __init__(self, socket_address: Optional[PathLike] = None) -> None:
        self.socket_address = socket_address
        self.barrier = threading.Barrier(2)

    @property
    @classmethod
    @abc.abstractmethod
    def endpoint(cls) -> "str":
        """The name of the API endpoint"""

    @abc.abstractmethod
    def _message(self, msg: Dict[str, Any], fds: jsoncomm.FdSet, sock: jsoncomm.Socket) -> None:
        """Called for a new incoming message

        The file descriptor set `fds` will be closed after the call.
        Use the `FdSet.steal()` method to extract file descriptors.
        """

    def _cleanup(self) -> None:
        """Called after the event loop is shut down"""

    @classmethod
    def _make_socket_dir(cls, rundir: PathLike = "/run/osbuild") -> tempfile.TemporaryDirectory[Any]:
        """Called to create the temporary socket dir"""
        os.makedirs(rundir, exist_ok=True)
        return tempfile.TemporaryDirectory(prefix="api-", dir=rundir)

    def _dispatch(self, sock: jsoncomm.Socket) -> None:
        """Called when data is available on the socket"""
        msg, fds, _ = sock.recv()
        if msg is None:
            # Peer closed the connection
            if self.event_loop:
                self.event_loop.remove_reader(sock)
            return
        self._message(msg, fds, sock)
        fds.close()

    def _accept(self, server: jsoncomm.Socket) -> None:
        client = server.accept()
        if client and self.event_loop:
            self.event_loop.add_reader(client, self._dispatch, client)

    def _run_event_loop(self) -> None:
        if not self.socket_address:
            raise RuntimeError("_run_event_loop but no socket_address")

        with jsoncomm.Socket.new_server(self.socket_address) as server:
            server.blocking = False
            server.listen()
            self.barrier.wait()

            if not self.event_loop:
                raise RuntimeError("_run_event_loop but no event_loop")

            self.event_loop.add_reader(server, self._accept, server)
            asyncio.set_event_loop(self.event_loop)
            self.event_loop.run_forever()
            self.event_loop.remove_reader(server)

    @property
    def running(self) -> bool:
        return self.event_loop is not None

    def __enter__(self) -> "BaseAPI":
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

    def __exit__(self, *args: List[Any]) -> None:
        if not self.event_loop:
            raise RuntimeError("__exit__ but no event_loop")

        self.event_loop.call_soon_threadsafe(self.event_loop.stop)

        if not self.thread:
            raise RuntimeError("__exit__ but no thread")

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

    error: Optional[Dict[str, Any]] = None

    def __init__(self, *, socket_address: Optional[PathLike] = None) -> None:
        super().__init__(socket_address)
        self.metadata = {}

    def _set_metadata(self, message: Dict[str, Any], fds: jsoncomm.FdSet) -> None:
        fd = message["metadata"]
        with os.fdopen(fds.steal(fd), encoding="utf-8") as f:
            data = json.load(f)
        self.metadata.update(data)

    def _get_exception(self, message: Dict[str, Any]) -> None:
        self.error = {
            "type": "exception",
            "data": message["exception"],
        }

    def _message(self, msg: Dict[str, Any], fds: jsoncomm.FdSet, sock: jsoncomm.Socket) -> None:
        if msg["method"] == 'add-metadata':
            self._set_metadata(msg, fds)
        elif msg["method"] == 'exception':
            self._get_exception(msg)


def exception(e: Type[BaseException], path: str = "/run/osbuild/api/osbuild") -> None:
    """Send exception to osbuild"""
    traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
    with jsoncomm.Socket.new_client(path) as client:
        with io.StringIO() as out:
            traceback.print_tb(e.__traceback__, file=out)
            stacktrace = out.getvalue()
        msg = {
            "method": "exception",
            "exception": {
                "type": type(e).__name__,
                "value": str(e),
                "traceback": stacktrace
            }
        }
        client.send(msg)

    sys.exit(2)


# pylint: disable=broad-except
@contextlib.contextmanager
def exception_handler(path: str = "/run/osbuild/api/osbuild") -> Iterator[None]:
    try:
        yield
    except Exception as e:
        exception(e, path)


def arguments(path: str = "/run/osbuild/api/arguments") -> Dict[str, Any]:
    """Retrieve the input arguments that were supplied to API"""
    with open(path, "r", encoding="utf-8") as fp:
        data: Dict[str, Any] = json.load(fp)
    return data


def metadata(data: Dict[str, Any], path: str = "/run/osbuild/api/osbuild") -> None:
    """Update metadata for the current module"""

    def data_to_file() -> io.TextIOWrapper:
        with tempfile.TemporaryFile() as f:
            f.write(json.dumps(data).encode('utf-8'))
            # re-open the file to get a read-only file descriptor
            return open(f"/proc/self/fd/{f.fileno()}", "r")

    with jsoncomm.Socket.new_client(path) as client, data_to_file() as f:
        msg = {
            "method": "add-metadata",
            "metadata": 0
        }
        client.send(msg, fds=[f.fileno()])
