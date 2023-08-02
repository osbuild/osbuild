#
# Test for API infrastructure
#

import json
import multiprocessing as mp
import os
import pathlib
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
                req = {"method": "echo", "data": "Hello"}
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

    def test_exception(self):
        # Check that 'api.exception' correctly sets 'API.exception'
        tmpdir = self.tmp.name
        path = os.path.join(tmpdir, "osbuild-api")

        def exception(path):
            with osbuild.api.exception_handler(path):
                raise ValueError("osbuild test exception")
            assert False, "api.exception should exit process"

        api = osbuild.api.API(socket_address=path)
        with api:
            p = mp.Process(target=exception, args=(path,))
            p.start()
            p.join()
        self.assertEqual(p.exitcode, 2)
        self.assertIsNotNone(api.error, "Error not set")
        self.assertIn("type", api.error, "Error has no 'type' set")
        self.assertEqual("exception", api.error["type"], "Not an exception")
        e = api.error["data"]
        for field in ("type", "value", "traceback"):
            self.assertIn(field, e, f"Exception needs '{field}'")
        self.assertEqual(e["value"], "osbuild test exception")
        self.assertEqual(e["type"], "ValueError")
        self.assertIn("exception", e["traceback"])

    def test_metadata(self):
        # Check that `api.metadata` leads to `API.metadata` being
        # set correctly
        tmpdir = self.tmp.name
        path = pathlib.Path(tmpdir, "metadata")
        path.touch()

        data = {"meta": "42"}
        osbuild.api.metadata(data, path=path)

        with open(path, "r", encoding="utf8") as f:
            metadata = json.load(f)

        assert metadata
        self.assertEqual(metadata, data)
