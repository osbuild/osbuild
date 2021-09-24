#!/usr/bin/python3

#
# Runtime Tests for Host Services
#

import errno
import os
import sys
import tempfile
from typing import Any

import pytest

from osbuild import host
from osbuild.util.jsoncomm import FdSet


class ServiceTest(host.Service):

    def __init__(self, args):
        super().__init__(args)
        self.fds = []

    def register_fds(self, fds):
        self.fds.extend(fds)

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


def main():
    service = ServiceTest.from_args(sys.argv[1:])
    service.main()


if __name__ == "__main__":
    main()
