#!/usr/bin/python3
"""
network related utilities
"""
import base64
import contextlib
import http.server
import socket
import ssl
import threading

try:
    from http.server import ThreadingHTTPServer
except ImportError:
    # This fallback is only needed on py3.6. Py3.7+ has ThreadingHTTPServer.
    # We just import ThreadingHTTPServer here so that the import of "net.py"
    # on py36 works, the helpers are not usable because the "directory" arg
    # for SimpleHTTPRequestHandler is also not supported.
    class ThreadingHTTPServer:  # type: ignore
        def __init__(self, *args, **kwargs):  # pylint: disable=unused-argument
            # pylint: disable=import-outside-toplevel
            import pytest  # type: ignore
            pytest.skip("python too old to suport ThreadingHTTPServer")


from .atomic import AtomicCounter


def _get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("localhost", 0))
    return s.getsockname()[1]


class SilentHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.basic_auth = kwargs.pop("basic_auth")
        super().__init__(*args, **kwargs)

    def log_message(self, *args, **kwargs):
        pass

    def do_GET(self):
        # silence errors when the other side "hangs up" unexpectedly
        # (our tests will do that when downloading in parallel)
        try:
            if self.basic_auth and self.headers.get("Authorization") != "Basic " + self.basic_auth:
                self.send_response(401)
            super().do_GET()
        except (ConnectionResetError, BrokenPipeError):
            pass


class DirHTTPServer(ThreadingHTTPServer):
    def __init__(self, *args, directory=None, simulate_failures=0, basic_auth=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.directory = directory
        self.simulate_failures = AtomicCounter(simulate_failures)
        self.reqs = AtomicCounter()
        self.basic_auth = basic_auth

    def finish_request(self, request, client_address):
        self.reqs.inc()
        if self.simulate_failures.count > 0:
            self.simulate_failures.dec()
            SilentHTTPRequestHandler(
                request, client_address, self, directory="does-not-exists", basic_auth=self.basic_auth)
            return
        SilentHTTPRequestHandler(
            request, client_address, self, directory=self.directory, basic_auth=self.basic_auth)


def _httpd(rootdir, simulate_failures, ctx=None, basic_auth=None):
    port = _get_free_port()
    httpd = DirHTTPServer(
        ("localhost", port),
        http.server.SimpleHTTPRequestHandler,
        directory=rootdir,
        simulate_failures=simulate_failures,
        basic_auth=basic_auth,
    )
    if ctx:
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    threading.Thread(target=httpd.serve_forever).start()
    return httpd


@contextlib.contextmanager
def http_serve_directory(rootdir, simulate_failures=0):
    httpd = _httpd(rootdir, simulate_failures)
    try:
        yield httpd
    finally:
        httpd.shutdown()


@contextlib.contextmanager
def http_serve_directory_basic_auth(rootdir, user, password, simulate_failures=0):
    httpd = _httpd(
        rootdir,
        simulate_failures,
        basic_auth=base64.b64encode(
            f"{user}:{password}".encode("utf-8")).decode())
    try:
        yield httpd
    finally:
        httpd.shutdown()


@contextlib.contextmanager
def https_serve_directory(rootdir, certfile, keyfile, simulate_failures=0):
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(certfile=certfile, keyfile=keyfile)
    httpd = _httpd(rootdir, simulate_failures, ctx)
    try:
        yield httpd
    finally:
        httpd.shutdown()


@contextlib.contextmanager
def https_serve_directory_mtls(rootdir, ca_cert, server_cert, server_key, simulate_failures=0):
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH, cafile=ca_cert)
    ctx.load_cert_chain(certfile=server_cert, keyfile=server_key)
    ctx.verify_mode = ssl.CERT_REQUIRED
    httpd = _httpd(rootdir, simulate_failures, ctx)
    try:
        yield httpd
    finally:
        httpd.shutdown()
