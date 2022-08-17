"""
Functionality provided by the host

The biggest functionality this module provides are so called host
services:

Stages run inside a container to isolate them from the host which
the build is run on. This means that the stages do not have direct
access to certain features offered by the host system, like access
to the network, devices as well as the osbuild store itself.

Host services are a way to provide functionality to stages that is
restricted to the host and not directly available in the container.

A service itself is an executable that gets spawned by osbuild on-
demand and communicates with osbuild via a simple JSON based IPC
protocol. To ease the development of such services the `Service`
class of this module can be used, which sets up and handles the
communication with the host.

On the host side a `ServiceManager` can be used to spawn and manage
concrete services. Specifically it functions as a context manager
and will shut down services when the context exits.

The `ServiceClient` class provides a client for the services and can
thus be used to interact with the service from the host side.

A note about host service lifetimes: The host service lifetime is
meant to be bound to the service it provides, e.g. when the service
provides data to a stage, it is meant that this data is accessible
for exactly as long as the binary is run and all resources must be
freed when the service is stopped.
The idea behind this design is to ensure that no resources get
leaked because only the host service itself is responsible for
their clean up, independent of any control of osbuild.
"""

import abc
import argparse
import asyncio
import fcntl
import importlib
import io
import os
import signal
import subprocess
import sys
import threading
import traceback
from collections import OrderedDict
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

from osbuild.util.jsoncomm import FdSet, Socket


class ProtocolError(Exception):
    """Errors concerning the communication between host and service"""


class RemoteError(Exception):
    """A RemoteError indicates an unexpected error in the service"""

    def __init__(self, name, value, stack) -> None:
        self.name = name
        self.value = value
        self.stack = stack
        msg = f"{name}: {value}\n {stack}"
        super().__init__(msg)


class ServiceProtocol:
    """
    Wire protocol between host and service

    The ServicePortocol specifies the wire protocol between the host
    and the service. It contains methods to translate messages into
    their wire format and back.
    """

    @staticmethod
    def decode_message(msg: Dict) -> Tuple[str, Dict]:
        if not msg:
            raise ProtocolError("message empty")

        t = msg.get("type")
        if not t:
            raise ProtocolError("'type' field missing")

        d = msg.get("data")
        if not d:
            raise ProtocolError("'data' field missing")
        return t, d

    @staticmethod
    def encode_method(name: str, arguments: Union[List[str], Dict[str, Any]]):
        msg = {
            "type": "method",
            "data": {
                "name": name,
                "args": arguments,
            }
        }
        return msg

    @staticmethod
    def decode_method(data: Dict):
        name = data.get("name")
        if not name:
            raise ProtocolError("'name' field missing")

        args = data.get("args", [])
        return name, args

    @staticmethod
    def encode_reply(reply: Any):
        msg = {
            "type": "reply",
            "data": {
                "reply": reply
            }
        }
        return msg

    @staticmethod
    def decode_reply(msg: Dict) -> Any:
        if "reply" not in msg:
            raise ProtocolError("'reply' field missing")

        data = msg["reply"]
        # NB: This is the returned data of the remote
        # method call, which can also be `None`
        return data

    @staticmethod
    def encode_signal(sig: Any):
        msg = {
            "type": "signal",
            "data": {
                "reply": sig
            }
        }
        return msg

    @staticmethod
    def encode_exception(value, tb):
        backtrace = "".join(traceback.format_tb(tb))
        msg = {
            "type": "exception",
            "data": {
                "name": value.__class__.__name__,
                "value": str(value),
                "backtrace": backtrace
            }
        }
        return msg

    @staticmethod
    def decode_exception(data):
        name = data["name"]
        value = data["value"]
        tb = data["backtrace"]

        return RemoteError(name, value, tb)


class Service(abc.ABC):
    """
    Host service

    This abstract base class provides all the base functionality to
    implement a host service. Specifically, it handles the setup of
    the service itself and the communication with osbuild.

    The `dispatch` method needs to be implemented by deriving
    classes to handle remote method calls.

    The `stop` method should be implemented to tear down state and
    free resources.
    """

    protocol = ServiceProtocol

    def __init__(self, args: argparse.Namespace):

        self.sock = Socket.new_from_fd(args.service_fd)
        self.id = args.service_id

    @classmethod
    def from_args(cls, argv):
        """Create a service object given an argument vector"""

        parser = cls.prepare_argument_parser()
        args = parser.parse_args(argv)
        return cls(args)

    @classmethod
    def prepare_argument_parser(cls):
        """Prepare the command line argument parser"""

        name = __class__.__name__

        desc = f"osbuild {name} host service"
        parser = argparse.ArgumentParser(description=desc)

        parser.add_argument("--service-fd", metavar="FD", type=int,
                            help="service file descriptor")
        parser.add_argument("--service-id", metavar="ID", type=str,
                            help="service identifier")
        return parser

    @abc.abstractmethod
    def dispatch(self, method: str, args: Any, fds: FdSet):
        """Handle remote method calls

        This method must be overridden in order to handle remote
        method calls. The incoming arguments are the method name,
        `method` and its arguments, `args`, together with a set
        of file descriptors (optional). The reply to this method
        will form the return value of the remote call.
        """

    def stop(self):
        """Service is stopping

        This method will be called when the service is stopping,
        and should be overridden to tear down state and free
        resources allocated by the service.

        NB: This method might be called at any time due to signals,
        even during the handling method calls.
        """

    def main(self):
        """Main service entry point

        This method should be invoked in the service executable
        to actually run the service. After additional setup this
        will call the `serve` method to wait for remote method
        calls.
        """

        # We ignore `SIGTERM` and `SIGINT` here, so that the
        # controlling process (osbuild) can shut down all host
        # services in a controlled fashion and in the correct
        # order by closing the communication socket.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        try:
            self.serve()
        finally:
            self.stop()

    def serve(self):
        """Serve remote requests

        Wait for remote method calls and translate them into
        calls to `dispatch`.
        """

        while True:
            msg, fds, _ = self.sock.recv()
            if not msg:
                break

            reply_fds = None
            try:
                reply, reply_fds = self._handle_message(msg, fds)

                # Catch invalid file descriptors early so that
                # we send an error reply instead of throwing
                # an exception in `sock.send` later.
                self._check_fds(reply_fds)

            except:  # pylint: disable=bare-except
                reply_fds = self._close_all(reply_fds)
                _, val, tb = sys.exc_info()
                reply = self.protocol.encode_exception(val, tb)

            finally:
                fds.close()

            try:
                self.sock.send(reply, fds=reply_fds)
            except BrokenPipeError:
                break
            finally:
                self._close_all(reply_fds)

    def _handle_message(self, msg, fds):
        """
        Internal method called by `service` to handle new messages
        """

        kind, data = self.protocol.decode_message(msg)

        if kind != "method":
            raise ProtocolError(f"unknown message type: {kind}")

        name, args = self.protocol.decode_method(data)
        ret, fds = self.dispatch(name, args, fds)
        msg = self.protocol.encode_reply(ret)

        return msg, fds

    def emit_signal(self, data: Any, fds: Optional[list] = None):
        self._check_fds(fds)
        self.sock.send(self.protocol.encode_signal(data), fds=fds)

    @staticmethod
    def _close_all(fds: Optional[List[int]]):
        if not fds:
            return []

        for fd in fds:
            try:
                os.close(fd)
            except OSError as e:
                print(f"error closing fd '{fd}': {e!s}")
        return []

    @staticmethod
    def _check_fds(fds: Optional[List[int]]):
        if not fds:
            return

        for fd in fds:
            fcntl.fcntl(fd, fcntl.F_GETFD)


class ServiceClient:
    """
    Host service client

    Can be used to remotely call methods on the host services. Normally
    returned from the `ServiceManager` when starting a new host service.
    """
    protocol = ServiceProtocol

    def __init__(self, uid, proc, sock):
        self.uid = uid
        self.proc = proc
        self.sock = sock

    def call(self, method: str, args: Optional[Any] = None) -> Any:
        """Remotely call a method and return the result"""

        ret, _ = self.call_with_fds(method, args)
        return ret

    def call_with_fds(self, method: str,
                      args: Optional[Union[List[str], Dict[str, Any]]] = None,
                      fds: Optional[List[int]] = None,
                      on_signal: Callable[[Any, Optional[Iterable[int]]], None] = None
                      ) -> Tuple[Any, Optional[Iterable[int]]]:
        """
        Remotely call a method and return the result, including file
        descriptors.
        """

        if args is None:
            args = []

        if fds is None:
            fds = []

        msg = self.protocol.encode_method(method, args)

        self.sock.send(msg, fds=fds)

        while True:
            ret, fds, _ = self.sock.recv()
            kind, data = self.protocol.decode_message(ret)
            if kind == "signal":
                ret = self.protocol.decode_reply(data)

                if on_signal:
                    on_signal(ret, fds)
            if kind == "reply":
                ret = self.protocol.decode_reply(data)
                return ret, fds
            if kind == "exception":
                error = self.protocol.decode_exception(data)
                raise error

        raise ProtocolError(f"unknown message type: {kind}")

    def stop(self):
        """
        Stop the host service associated with this client.
        """

        self.sock.close()
        self.proc.wait()


class ServiceManager:
    """
    Host service manager

    Manager, i.e. `start` and `stop` host services. Must be used as a
    context manager. When the context is active, host services can be
    started via the `start` method.

    When a `monitor` is provided, stdout and stderr of the service will
    be forwarded to the monitor via `monitor.log`, otherwise sys.stdout
    is used.
    """

    def __init__(self, *, monitor=None):
        self.services = OrderedDict()
        self.monitor = monitor

        self.barrier = threading.Barrier(2)
        self.event_loop = None
        self.thread = None

    @property
    def running(self):
        """Return whether the service manager is running"""
        return self.event_loop is not None

    @staticmethod
    def make_env():
        # We want the `osbuild` python package that contains this
        # very module, which might be different from the system wide
        # installed one, to be accessible to the Input programs so
        # we detect our origin and set the `PYTHONPATH` accordingly
        modorigin = importlib.util.find_spec("osbuild").origin
        modpath = os.path.dirname(modorigin)
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.dirname(modpath)
        env["PYTHONUNBUFFERED"] = "1"
        return env

    def start(self, uid, cmd, extra_args=None) -> ServiceClient:
        """
        Start a new host service

        Create a new host service with the unique identifier `uid` by
        spawning the executable provided via `cmd` with optional extra
        arguments `extra_args`.

        The return value is a `ServiceClient` instance that is already
        connected to the service and can thus be used to call methods.

        NB: Must be called with an active context
        """

        if not self.running:
            raise RuntimeError("ServiceManager not running")

        if uid in self.services:
            raise ValueError(f"{uid} already started")

        ours, theirs = Socket.new_pair()
        env = self.make_env()

        try:
            fd = theirs.fileno()
            argv = [
                cmd,
                "--service-id", uid,
                "--service-fd", str(fd)
            ]

            if extra_args:
                argv += extra_args

            proc = subprocess.Popen(argv,
                                    env=env,
                                    stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    bufsize=0,
                                    pass_fds=(fd, ),
                                    close_fds=True)

            service = ServiceClient(uid, proc, ours)
            self.services[uid] = service
            ours = None

            if proc.stdout is None:
                raise RuntimeError("No stdout.")

            stdout = io.TextIOWrapper(proc.stdout,
                                      encoding="utf-8",
                                      line_buffering=True)

            name = os.path.basename(cmd)

            def reader():
                return self._stdout_ready(name, uid, stdout)

            self.event_loop.add_reader(stdout, reader)

        finally:
            if ours:
                ours.close()

        return service

    def stop(self, uid):
        """
        Stop a service given its unique identifier, `uid`
        """

        service = self.services.get(uid)
        if not service:
            raise ValueError(f"unknown service: {uid}")

        service.stop()

    def _stdout_ready(self, name, uid, stdout):
        txt = stdout.readline()
        if not txt:
            self.event_loop.remove_reader(stdout)
            return

        msg = f"{uid} ({name}): {txt}"
        if self.monitor:
            self.monitor.log(msg)
        else:
            print(msg, end="")

    def _thread_main(self):
        self.barrier.wait()
        asyncio.set_event_loop(self.event_loop)
        self.event_loop.run_forever()

    def __enter__(self):
        # We are not re-entrant, so complain if re-entered.
        assert not self.running

        self.event_loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._thread_main)

        self.barrier.reset()
        self.thread.start()
        self.barrier.wait()

        return self

    def __exit__(self, *args):
        # Stop all registered services
        while self.services:
            _, srv = self.services.popitem()
            srv.stop()

        self.event_loop.call_soon_threadsafe(self.event_loop.stop)
        self.thread.join()
        self.event_loop.close()
