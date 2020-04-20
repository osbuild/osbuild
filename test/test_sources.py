import contextlib
import ctypes
import http.server
import json
import os
import socketserver
import subprocess
import tempfile
import threading
import unittest

import osbuild.sources

def errcheck(ret, _func, _args):
    if ret == -1:
        e = ctypes.get_errno()
        raise OSError(e, os.strerror(e))


CLONE_NEWNET = 0x40000000
libc = ctypes.CDLL('libc.so.6', use_errno=True)
libc.setns.errcheck = errcheck


@contextlib.contextmanager
def netns():
    # Grab a reference to the current namespace.
    with open("/proc/self/ns/net") as oldnet:
        # Create a new namespace and enter it.
        libc.unshare(CLONE_NEWNET)
        # Up the loopback device in the new namespace.
        subprocess.run(["ip", "link", "set", "up", "dev", "lo"], check=True)
        try:
            yield
        finally:
            # Revert to the old namespace, dropping our
            # reference to the new one.
            libc.setns(oldnet.fileno(), CLONE_NEWNET)


@contextlib.contextmanager
def fileServer():
    with netns():
        # This is leaked until the program exits, but inaccessible after the with
        # due to the network namespace.
        barrier = threading.Barrier(2)
        thread = threading.Thread(target=runFileServer, args=(barrier,))
        thread.daemon = True
        thread.start()
        barrier.wait()
        yield


def runFileServer(barrier):
    httpd = socketserver.TCPServer(('', 80), http.server.SimpleHTTPRequestHandler)
    barrier.wait()
    httpd.serve_forever()


class TestSources(unittest.TestCase):
    def setUp(self):
        self.sources = 'test/sources_tests'


    def check_case(self, source, case, api_path):
        expects = case["expects"]
        if expects == "error":
            with self.assertRaises(RuntimeError):
                osbuild.sources.get(source, case["checksums"], api_path=api_path)
        elif expects == "success":
            r = osbuild.sources.get(source, case["checksums"], api_path=api_path)
            self.assertEqual(r, {})
        else:
            raise ValueError(f"invalid expectation: {expects}")


    def check_source(self, source):
        source_options = {}
        with open(f"{self.sources}/{source}/sources.json") as f:
            source_options = json.load(f)
        for case in os.listdir(f"{self.sources}/{source}/cases"):
            with self.subTest(case=case):
                case_options = {}
                with open(f"{self.sources}/{source}/cases/{case}") as f:
                    case_options = json.load(f)
                with tempfile.TemporaryDirectory() as tmpdir, \
                    fileServer(), \
                    osbuild.sources.SourcesServer(
                            f"{tmpdir}/sources-api",
                            "./sources", source_options,
                            f"{tmpdir}/cache", f"{tmpdir}/dst"):
                    self.check_case(source, case_options, f"{tmpdir}/sources-api")
                    self.check_case(source, case_options, f"{tmpdir}/sources-api")


    def test_sources(self):
        for source in os.listdir(self.sources):
            with self.subTest(source=source):
                self.check_source(source)
