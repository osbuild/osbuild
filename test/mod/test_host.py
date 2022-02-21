#!/usr/bin/python3

#
# Runtime Tests for Host Services
#

import errno
import os
import sys
import tempfile
from typing import Any, Dict

import pytest

from osbuild import host
from osbuild.util.jsoncomm import FdSet


class DummySerializedInfo(host.AbstractSerializableObject):

    def __init__(self, a=None, b=None):
        self.a = a
        self.b = b

    def _to_dict(self) -> Dict:
        return {"a": self.a, "b": self.b}

    def _from_dict(self, obj: Dict):
        self.a = obj["a"]
        self.b = obj["b"]


class ServiceTest(host.Service):

    def __init__(self, args):
        super().__init__(args)
        self.fds = []

    def register_fds(self, fds):
        self.fds.extend(fds)

    # pylint: disable=too-many-branches
    def dispatch(self, method: str, args: Any, fds: FdSet):
        ret = None

        if method == "exception":
            raise ValueError("Remote Exception")
        if method == "echo":
            ret = args
        elif method == "echo-fd":
            ret = args
            with tempfile.TemporaryFile("w+") as f:
                with os.fdopen(fds.steal(0)) as d:
                    f.write(d.read())
                f.seek(0)
                fds = [os.dup(f.fileno())]
                self.register_fds(fds)

        elif method == "identify":
            ret = self.id
        elif method == "invalid-fd":
            ret = []
            with tempfile.TemporaryFile("w+") as f:
                valid_fd = os.dup(f.fileno())
            invalid_fd = valid_fd + 10
            fds = [valid_fd, invalid_fd]
            self.register_fds([valid_fd])
        elif method == "check-fds-are-closed":
            while self.fds:
                fd = self.fds.pop()
                try:
                    os.close(fd)
                except OSError as e:
                    if e.errno == errno.EBADF:
                        print(f"fd '{fd}' was closed")
                        continue
                    raise
                raise ValueError(f"fd '{fd}' was not closed")
        elif method == "signal_me_3_times":
            self.emit_signal(0)
            self.emit_signal(1)
            self.emit_signal(2)
        elif method == "signal_me_on_fd":
            with tempfile.TemporaryFile("w+") as f:
                with os.fdopen(fds.steal(0)) as d:
                    f.write(d.read())
                f.seek(0)
                fds = [os.dup(f.fileno())]
                self.register_fds(fds)
                self.emit_signal("that should do it", fds)
        elif method == "serialized_object":
            ret = DummySerializedInfo(args[0], args[1]).to_dict()
            return ret, fds
        else:
            raise host.ProtocolError("unknown method:", method)

        return ret, fds


def test_basic():
    with host.ServiceManager() as mgr:
        for i in range(3):
            client = mgr.start(str(i), __file__)

            args = ["an", "argument"]
            res = client.call("echo", args)

            assert args == res

            remote_id = client.call("identify")
            assert remote_id == str(i)

            with pytest.raises(ValueError, match=f"{str(i)}"):
                _ = mgr.start(str(i), __file__)

        for i in range(3):
            client = mgr.services[str(i)]
            client.stop()


def test_pass_fd():
    with host.ServiceManager() as mgr:
        for i in range(3):
            client = mgr.start(str(i), __file__)

            args = ["an", "argument"]
            data = "osbuild\n"

            with tempfile.TemporaryFile("w+") as f:
                f.write(data)
                f.seek(0)

                res, fds = client.call_with_fds("echo-fd", args, fds=[f.fileno()])

            assert args == res
            with os.fdopen(fds.steal(0)) as d:
                assert data == d.read()

            client.call_with_fds("check-fds-are-closed")

            remote_id = client.call("identify")
            assert remote_id == str(i)

            with pytest.raises(ValueError, match=f"{str(i)}"):
                _ = mgr.start(str(i), __file__)

        for i in range(3):
            client = mgr.services[str(i)]
            client.stop()


def test_pass_fd_invalid():
    with host.ServiceManager() as mgr:

        client = mgr.start(str("test-invalid-fd"), __file__)
        with pytest.raises(host.RemoteError):
            client.call_with_fds("invalid-fd")
        client.call_with_fds("check-fds-are-closed")


def test_exception():
    with host.ServiceManager() as mgr:
        client = mgr.start("exception", __file__)
        with pytest.raises(host.RemoteError, match=r"Remote Exception"):
            client.call("exception")


def test_signals():
    with host.ServiceManager() as mgr:
        exec_callback = 0

        def check_value(item, _fds):
            nonlocal exec_callback
            assert item == exec_callback
            exec_callback += 1
        client = mgr.start("test_signal_me_3_times", __file__)
        client.call_with_fds("signal_me_3_times", on_signal=check_value)
        assert exec_callback == 3


def test_signals_on_separate_fd():
    with host.ServiceManager() as mgr:

        data = "osbuild\n"
        exec_callback = False

        def check_value(item, fds):
            nonlocal exec_callback
            exec_callback = True
            assert item == "that should do it"
            with os.fdopen(fds.steal(0)) as d:
                assert data == d.read()

        client = mgr.start("test_signal_me_on_fd", __file__)

        with tempfile.TemporaryFile("w+") as f:
            f.write(data)
            f.seek(0)

            client.call_with_fds("signal_me_on_fd", fds=[f.fileno()], on_signal=check_value)
        assert exec_callback


def test_serialized():
    with host.ServiceManager() as mgr:
        for i in range(3):
            client = mgr.start(str(i), __file__)

            args = [i, i+1]

            res, _ = client.call_with_fds("serialized_object", args)
            ret = host.AbstractSerializableObject.from_dict(res)
            # the two classes come from different modules, then they should be different
            assert ret.__class__ != DummySerializedInfo
            # but they should also have the same name
            assert ret.__class__.__name__ == DummySerializedInfo.__name__
            assert ret.a == i
            assert ret.b == i+1


def main():
    service = ServiceTest.from_args(sys.argv[1:])
    service.main()


if __name__ == "__main__":
    main()
