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

import osbuild.objectstore
import osbuild.meta
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


def check_case(source, case, store, libdir):
    expects = case["expects"]
    if expects == "error":
        with pytest.raises(RuntimeError):
            source.download(store, libdir)
    elif expects == "success":
        source.download(store, libdir)
    else:
        raise ValueError(f"invalid expectation: {expects}")


def check_source(source, sources):
    index = osbuild.meta.Index(os.curdir)

    for case in os.listdir(f"{sources}/{source}/cases"):
        with open(f"{sources}/{source}/cases/{case}") as f:
            case_options = json.load(f)

        info = index.get_module_info("Source", source)
        desc = case_options[source]
        items = desc.get("items", {})
        options = desc.get("options", {})

        src = osbuild.sources.Source(info, items, options)

        with tempfile.TemporaryDirectory() as tmpdir, \
            osbuild.objectstore.ObjectStore(tmpdir) as store, \
                fileServer(test.TestBase.locate_test_data()):
            check_case(src, case_options, store, index.path)
            check_case(src, case_options, store, index.path)


@pytest.mark.skipif(not test.TestBase.have_test_data(), reason="no test-data access")
@pytest.mark.skipif(not can_setup_netns(), reason="network namespace setup failed")
def test_sources():
    sources = os.path.join(test.TestBase.locate_test_data(), "sources")

    for source in os.listdir(sources):
        check_source(source, sources)
