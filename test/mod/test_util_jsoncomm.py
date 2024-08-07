#
# Tests for the 'osbuild.util.jsoncomm' module.
#

# pylint: disable=protected-access

import asyncio
import errno
import json
import os
import pathlib
import tempfile
import unittest
from concurrent import futures
from unittest.mock import patch

import pytest

from osbuild.util import jsoncomm


class TestUtilJsonComm(unittest.TestCase):
    def setUp(self):
        # Prepare a bi-directional connection between a `client`
        # and `server`; nb: the nomenclature is a bit unusual in
        # the sense that the serving socket is called `listener`
        self.dir = tempfile.TemporaryDirectory()
        self.address = pathlib.Path(self.dir.name, "listener")
        self.listener = jsoncomm.Socket.new_server(self.address)
        self.listener.blocking = True  # We want `accept` to block
        self.listener.listen()

        with futures.ThreadPoolExecutor() as executor:
            future = executor.submit(self.listener.accept)
            self.client = jsoncomm.Socket.new_client(self.address)
            self.server = future.result()

    def tearDown(self):
        self.client.close()
        self.server.close()
        self.listener.close()
        self.dir.cleanup()

    def test_fdset(self):
        #
        # Test the FdSet implementation. Create a simple FD array and verify
        # that the FdSet correctly indexes them. Furthermore, verify that a
        # close actually closes the Fds so a following FdSet will get the same
        # FD numbers assigned.
        #

        v1 = [os.dup(0), os.dup(0), os.dup(0), os.dup(0)]
        s = jsoncomm.FdSet.from_list(v1)
        assert len(s) == 4
        for i in range(4):
            assert s[i] == v1[i]
        with self.assertRaises(IndexError):
            _ = s[128]
        s.close()

        v2 = [os.dup(0), os.dup(0), os.dup(0), os.dup(0)]
        assert v1 == v2
        s = jsoncomm.FdSet.from_list(v2)
        s.close()

    def test_fdset_init(self):
        #
        # Test FdSet initializations. This includes common edge-cases like empty
        # initializers, invalid array values, or invalid types.
        #

        s = jsoncomm.FdSet.from_list([])
        s.close()

        with self.assertRaises(ValueError):
            v1 = [-1]
            s = jsoncomm.FdSet.from_list(v1)

        with self.assertRaises(ValueError):
            v1 = ["foobar"]
            s = jsoncomm.FdSet(rawfds=v1)

    def test_ping_pong(self):
        #
        # Test sending messages through the client/server connection.
        #

        data = {"key": "value"}
        self.client.send(data)
        msg = self.server.recv()
        assert msg[0] == data
        assert len(msg[1]) == 0

        self.server.send(data)
        msg = self.client.recv()
        assert msg[0] == data
        assert len(msg[1]) == 0

    def test_scm_rights(self):
        #
        # Test FD transmission. Create a file, send a file-descriptor through
        # the communication channel, and then verify that the file-contents
        # can be read.
        #

        with tempfile.TemporaryFile() as f1:
            f1.write(b"foobar")
            f1.seek(0)

            self.client.send({}, fds=[f1.fileno()])

            msg = self.server.recv()
            assert msg[0] == {}
            assert len(msg[1]) == 1
            with os.fdopen(msg[1].steal(0)) as f2:
                assert f2.read() == "foobar"

    def test_listener_cleanup(self):
        #
        # Verify that only a single server can listen on a specified address.
        # Then make sure closing a server will correctly unlink its socket.
        #

        addr = os.path.join(self.dir.name, "foobar")
        srv1 = jsoncomm.Socket.new_server(addr)
        with self.assertRaises(OSError):
            srv2 = jsoncomm.Socket.new_server(addr)
        srv1.close()
        srv2 = jsoncomm.Socket.new_server(addr)
        srv2.close()

    def test_contextlib(self):
        #
        # Verify the context-manager of sockets. Make sure they correctly close
        # the socket, and they correctly propagate exceptions.
        #

        assert self.client.fileno() >= 0
        with self.client as client:
            assert client == self.client
            assert client.fileno() >= 0
        with self.assertRaises(AssertionError):
            self.client.fileno()

        assert self.server.fileno() >= 0
        with self.assertRaises(SystemError):
            with self.server as server:
                assert server.fileno() >= 0
                raise SystemError
            raise AssertionError
        with self.assertRaises(AssertionError):
            self.server.fileno()

    def test_asyncio(self):
        #
        # Test integration with asyncio-eventloops. Use a trivial echo server
        # and test a simple ping/pong roundtrip.
        #

        loop = asyncio.new_event_loop()

        def echo(socket):
            msg = socket.recv()
            socket.send(msg[0])
            loop.stop()

        self.client.send({})

        loop.add_reader(self.server, echo, self.server)
        loop.run_forever()
        loop.close()

        msg = self.client.recv()
        assert msg[0] == {}

    def test_accept_timeout(self):
        #
        # Test calling `accept` without any connection being ready to be
        # established will not throw any exceptions but return `None`
        address = pathlib.Path(self.dir.name, "noblock")
        listener = jsoncomm.Socket.new_server(address)
        listener.listen()

        conn = listener.accept()
        self.assertIsNone(conn)

    def test_socket_pair(self):
        #
        # Test creating a socket pair and sending, receiving of a simple message
        a, b = jsoncomm.Socket.new_pair()

        ping = {"osbuild": "yes"}
        a.send(ping)
        pong, _, _ = b.recv()
        self.assertEqual(ping, pong)

    def test_from_fd(self):
        #
        # Test creating a Socket from an existing file descriptor
        a, x = jsoncomm.Socket.new_pair()
        fd = os.dup(x.fileno())

        b = jsoncomm.Socket.new_from_fd(fd)

        # x should be closed and thus raise "Bad file descriptor"
        with self.assertRaises(OSError):
            os.write(fd, b"test")

        ping = {"osbuild": "yes"}
        a.send(ping)
        pong, _, _ = b.recv()
        self.assertEqual(ping, pong)

    def test_send_and_recv(self):
        #
        # Test for the send and receive helper method

        a, b = jsoncomm.Socket.new_pair()

        ping = {"osbuild": "yes"}
        a.send(ping)
        pong, _, _ = b.send_and_recv(ping)
        self.assertEqual(ping, pong)
        pong, _, _ = a.recv()
        self.assertEqual(ping, pong)

    def test_sendmsg_errors_with_size_on_EMSGSIZE(self):
        a, _ = jsoncomm.Socket.new_pair()

        serialized = json.dumps({"data": "1" * 1_000_000}).encode()
        with pytest.raises(BufferError) as exc:
            a._send_via_sendmsg(serialized, [])
        assert str(exc.value) == "jsoncomm message size 1000012 is too big"
        assert exc.value.__cause__.errno == errno.EMSGSIZE

    def test_send_and_recv_tons_of_data_is_fine(self):
        a, b = jsoncomm.Socket.new_pair()

        ping = {"data": "tons" * 1_000_000}
        a.send(ping)
        pong, _, _ = b.send_and_recv(ping)
        self.assertEqual(ping, pong)
        pong, _, _ = a.recv()
        self.assertEqual(ping, pong)

    def test_send_small_data_via_sendmsg(self):
        a, _ = jsoncomm.Socket.new_pair()
        with patch.object(a, "_send_via_fd") as mock_send_via_fd, \
                patch.object(a, "_send_via_sendmsg") as mock_send_via_sendmsg:
            ping = {"data": "little"}
            a.send(ping)
        assert mock_send_via_fd.call_count == 0
        assert mock_send_via_sendmsg.call_count == 1

    def test_send_huge_data_via_fd(self):
        a, _ = jsoncomm.Socket.new_pair()
        with patch.object(a, "_send_via_fd") as mock_send_via_fd, \
                patch.object(a, "_send_via_sendmsg") as mock_send_via_sendmsg:
            ping = {"data": "tons" * 1_000_000}
            a.send(ping)
        assert mock_send_via_fd.call_count == 1
        assert mock_send_via_sendmsg.call_count == 0
