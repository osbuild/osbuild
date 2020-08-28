#
# Test for API infrastructure
#

import os
import multiprocessing as mp
import sys
import tempfile
import unittest

import osbuild
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

    def test_get_arguments(self):
        tmpdir = self.tmp.name
        path = os.path.join(tmpdir, "osbuild-api")
        args = {"options": {"answer": 42}}
        monitor = osbuild.monitor.BaseMonitor(sys.stderr.fileno())

        with osbuild.api.API(args, monitor, socket_address=path) as _:
            data = osbuild.api.arguments(path=path)
            self.assertEqual(data, args)


    def test_metadata(self):
        # Check that `api.metadata` leads to `API.metadata` being
        # set correctly
        tmpdir = self.tmp.name
        path = os.path.join(tmpdir, "osbuild-api")
        args = {}
        monitor = osbuild.monitor.BaseMonitor(sys.stderr.fileno())

        def metadata(path):
            data = {"meta": "42"}
            osbuild.api.metadata(data, path=path)
            return 0

        api = osbuild.api.API(args, monitor, socket_address=path)
        with api:
            p = mp.Process(target=metadata, args=(path, ))
            p.start()
            p.join()
            self.assertEqual(p.exitcode, 0)
        metadata = api.metadata  # pylint: disable=no-member
        assert metadata
        self.assertEqual(metadata, {"meta": "42"})
