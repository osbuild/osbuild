import os.path
import pathlib
import subprocess

from osbuild.testutil import make_fake_tree
from osbuild.testutil.net import http_serve_directory, https_serve_directory


def test_http_serve_directory_smoke(tmp_path):
    make_fake_tree(tmp_path, {
        "file1": "file1 content",
        "dir1/file2": "file2 content",
    })
    with http_serve_directory(tmp_path) as httpd:
        output = subprocess.check_output(
            ["curl", f"http://localhost:{httpd.server_port}/file1"])
        assert output == b"file1 content"
        output = subprocess.check_output(
            ["curl", f"http://localhost:{httpd.server_port}/dir1/file2"])
        assert output == b"file2 content"


def test_https_serve_directory_smoke(tmp_path):
    make_fake_tree(tmp_path, {
        "file1": "file1 content",
    })
    cert_dir = pathlib.Path(__file__).parent.parent / "data/certs"
    cacertfile = cert_dir / "cert1.pem"
    assert cacertfile.exists()
    keyfile = cert_dir / "key1.pem"
    assert keyfile.exists()

    with https_serve_directory(tmp_path, cacertfile, keyfile) as httpd:
        output = subprocess.check_output(
            ["curl",
             "--cacert", os.fspath(cacertfile),
             f"https://localhost:{httpd.server_port}/file1"],
        )
        assert output == b"file1 content"
