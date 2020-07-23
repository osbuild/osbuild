#
# Test for API infrastructure
#

import os
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

    def _dispatch(self, server):
        msg, _, addr = server.recv()
        self.messages += 1

        if msg["method"] == "echo":
            msg["method"] = "reply"
            server.send(msg, destination=addr)

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
