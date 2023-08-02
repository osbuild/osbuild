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

import osbuild.meta
import osbuild.objectstore
import osbuild.sources
from osbuild import host

from .. import test


def errcheck(ret, _func, _args):
    if ret == -1:
        e = ctypes.get_errno()
        raise OSError(e, os.strerror(e))


CLONE_NEWNET = 0x40000000
libc = ctypes.CDLL("libc.so.6", use_errno=True)
libc.setns.errcheck = errcheck


@contextlib.contextmanager
def netns():
    # Grab a reference to the current namespace.
    with open("/proc/self/ns/net", encoding="utf8") as oldnet:
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
            super().__init__(request, client_address, server)

        def translate_path(self, path: str) -> str:
            translated_path = super().translate_path(path)
            common = os.path.commonpath([translated_path, directory])
            translated_path = os.path.join(directory, os.path.relpath(translated_path, common))
            return translated_path

        def guess_type(self, path):
            try:
                with open(path + ".mimetype", "r", encoding="utf8") as f:
                    return f.read().strip()
            except FileNotFoundError:
                pass
            return super().guess_type(path)

    httpd = socketserver.TCPServer(("", 80), Handler)
    barrier.wait()
    httpd.serve_forever()


def make_test_cases():
    sources = os.path.join(test.TestBase.locate_test_data(), "sources")
    if os.path.exists(sources):
        for source in os.listdir(sources):
            for case in os.listdir(f"{sources}/{source}/cases"):
                yield source, case


def check_case(source, case, store, libdir):
    with host.ServiceManager() as mgr:
        expects = case["expects"]
        if expects == "error":
            with pytest.raises(host.RemoteError):
                source.download(mgr, store, libdir)
        elif expects == "success":
            source.download(mgr, store, libdir)
        else:
            raise ValueError(f"invalid expectation: {expects}")


@pytest.fixture(name="tmpdir")
def tmpdir_fixture():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.mark.skipif(not can_setup_netns(), reason="network namespace setup failed")
@pytest.mark.parametrize("source,case", make_test_cases())
def test_sources(source, case, tmpdir):
    index = osbuild.meta.Index(os.curdir)
    sources = os.path.join(test.TestBase.locate_test_data(), "sources")

    with open(f"{sources}/{source}/cases/{case}", encoding="utf8") as f:
        case_options = json.load(f)

    info = index.get_module_info("Source", source)
    desc = case_options[source]
    items = desc.get("items", {})
    options = desc.get("options", {})

    src = osbuild.sources.Source(info, items, options)

    with osbuild.objectstore.ObjectStore(tmpdir) as store, fileServer(test.TestBase.locate_test_data()):
        check_case(src, case_options, store, index.path)
        check_case(src, case_options, store, index.path)
