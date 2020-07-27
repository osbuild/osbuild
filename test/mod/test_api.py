#
# Test for API infrastructure
#

import pathlib
import os
import sys
import tempfile
import unittest

import osbuild
from osbuild.buildroot import BuildRoot
from osbuild.monitor import NullMonitor
from osbuild.util import jsoncomm


class APITester(osbuild.api.BaseAPI):
    """Records the number of messages and if it got cleaned up"""
    def __init__(self, sockaddr):
        super().__init__(sockaddr)
        self.clean = False
        self.messages = 0

    endpoint = "test-api"

    def _message(self, msg, _fds, sock):
        self.messages += 1

        if msg["method"] == "echo":
            msg["method"] = "reply"
            sock.send(msg)

    def _cleanup(self):
        self.clean = True


class TestAPI(unittest.TestCase):
    """Check API infrastructure"""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_basic(self):
        # Basic API communication and cleanup checks

        socket = os.path.join(self.tmp.name, "socket")
        api = APITester(socket)
        with api:
            with jsoncomm.Socket.new_client(socket) as client:
                req = {'method': 'echo', 'data': 'Hello'}
                client.send(req)
                msg, _, _ = client.recv()
                self.assertEqual(msg["method"], "reply")
                self.assertEqual(req["data"], msg["data"])

        self.assertEqual(api.clean, True)
        self.assertEqual(api.messages, 1)

        # Assert proper cleanup
        self.assertIsNone(api.thread)
        self.assertIsNone(api.event_loop)

    def test_reentrancy_guard(self):
        socket = os.path.join(self.tmp.name, "socket")
        api = APITester(socket)
        with api:
            with self.assertRaises(AssertionError):
                with api:
                    pass

    def test_buildroot(self):
        # Check API and BuildRoot integration: the runner will call
        # api.setup_stdio and thus check that connecting to the api
        # works correctly
        runner = "org.osbuild.linux"
        libdir = os.path.abspath(os.curdir)
        var = pathlib.Path(self.tmp.name, "var")
        var.mkdir()

        monitor = NullMonitor(sys.stderr.fileno())
        with BuildRoot("/", runner, libdir=libdir, var=var) as root:
            api = osbuild.api.API({}, monitor)
            root.register_api(api)

            r = root.run(["/usr/bin/true"])
            self.assertEqual(r.returncode, 0)

            # Test we can use `.run` multiple times
            r = root.run(["/usr/bin/true"])
            self.assertEqual(r.returncode, 0)

            r = root.run(["/usr/bin/false"])
            self.assertNotEqual(r.returncode, 0)
