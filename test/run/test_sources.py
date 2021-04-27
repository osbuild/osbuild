#
# Runtime Tests for Source Modules
#

import contextlib
import ctypes
import http.server
import json
import os
import socketserver
import subprocess
import tempfile
import threading

import pytest

import osbuild.sources
from .. import test


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
        try:
            # Up the loopback device in the new namespace.
            subprocess.run(["ip", "link", "set", "up", "dev", "lo"], check=True)
            yield
        finally:
            # Revert to the old namespace, dropping our
            # reference to the new one.
            libc.setns(oldnet.fileno(), CLONE_NEWNET)


@contextlib.contextmanager
def fileServer(directory):
    with netns():
        # This is leaked until the program exits, but inaccessible after the with
        # due to the network namespace.
        barrier = threading.Barrier(2)
        thread = threading.Thread(target=runFileServer, args=(barrier, directory))
        thread.daemon = True
        thread.start()
        barrier.wait()
        yield


def can_setup_netns() -> bool:
    try:
        with netns():
            return True
    except:  # pylint: disable=bare-except
        return False


def runFileServer(barrier, directory):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, request, client_address, server):
            super().__init__(request, client_address, server, directory=directory)

    httpd = socketserver.TCPServer(('', 80), Handler)
    barrier.wait()
    httpd.serve_forever()


def check_case(source, case, api_path):
    expects = case["expects"]
    if expects == "error":
        with pytest.raises(RuntimeError):
            osbuild.sources.get(
                source, case["checksums"], api_path=api_path)
    elif expects == "success":
        r = osbuild.sources.get(
            source, case["checksums"], api_path=api_path)
        assert r == {}
    else:
        raise ValueError(f"invalid expectation: {expects}")


def check_source(source, sources):
    source_options = {}
    with open(f"{sources}/{source}/sources.json") as f:
        source_options = json.load(f)
    for case in os.listdir(f"{sources}/{source}/cases"):
        case_options = {}
        with open(f"{sources}/{source}/cases/{case}") as f:
            case_options = json.load(f)
        with tempfile.TemporaryDirectory() as tmpdir, \
            fileServer(test.TestBase.locate_test_data()), \
            osbuild.sources.SourcesServer(
            "./", source_options,
            f"{tmpdir}/cache", f"{tmpdir}/dst",
                socket_address=f"{tmpdir}/sources-api"):
            check_case(source, case_options, f"{tmpdir}/sources-api")
            check_case(source, case_options, f"{tmpdir}/sources-api")


@pytest.mark.skipif(not test.TestBase.have_test_data(), reason="no test-data access")
@pytest.mark.skipif(not can_setup_netns(), reason="network namespace setup failed")
def test_sources():
    sources = os.path.join(test.TestBase.locate_test_data(), "sources")

    for source in os.listdir(sources):
        check_source(source, sources)
