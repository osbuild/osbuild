"""
Common test fixtures for the osbuild.

Note that we have unit tests scattered across multiple directories, so we need
to put fixtures shared across multiple directories in this file.
"""

import os
import socket
import subprocess as sp
import time
import urllib.request

import pytest

"""Test repository paths"""
TEST_REPO_PATHS = [
    "./test/data/testrepos/baseos/",
    "./test/data/testrepos/appstream/",
    "./test/data/testrepos/custom/",
]


def _get_rand_port():
    """Get a random port"""
    s = socket.socket()
    s.bind(("", 0))
    return s.getsockname()[1]


def _wait_for_server(address, timeout=10):
    """Wait for HTTP server to be ready"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(address, timeout=1) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            time.sleep(0.1)
    raise TimeoutError(f"Server at {address} did not start within {timeout} seconds")


@pytest.fixture(name="repo_servers", scope="module")
def repo_servers_fixture():
    """Fixture to start test repository servers"""
    procs = []
    addresses = []
    for path in TEST_REPO_PATHS:
        port = _get_rand_port()  # this is racy, but should be okay
        p = sp.Popen(["python3", "-m", "http.server", str(port)], cwd=path, stdout=sp.PIPE, stderr=sp.DEVNULL)
        procs.append(p)
        # use last path component as name
        name = os.path.basename(path.rstrip("/"))
        address = f"http://localhost:{port}"
        addresses.append({"name": name, "address": address})
        # NB: we need to wait for the server to be ready before we can use it
        _wait_for_server(address)
    yield addresses
    for p in procs:
        p.kill()
