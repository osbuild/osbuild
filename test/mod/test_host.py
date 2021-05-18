#!/usr/bin/python3

#
# Runtime Tests for Host Services
#

import sys
from typing import Any

import pytest

from osbuild import host
from osbuild.util.jsoncomm import FdSet


class ServiceTest(host.Service):

    def dispatch(self, method: str, args: Any, fds: FdSet):
        ret, fds = None, None

        if method == "exception":
            raise ValueError("Remote Exception")
        if method == "echo":
            ret = args
        elif method == "identify":
            ret = self.id
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
