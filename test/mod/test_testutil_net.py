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


def test_http_ssl_serve_directory_smoke(tmp_path):
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


def test_http_ssl_serve_directory_multi_cert(tmp_path):
    httpd_dir1 = tmp_path / "httpd1"
    make_fake_tree(httpd_dir1, {
        "file1": "file1 content",
    })
    httpd_dir2 = tmp_path / "httpd2"
    make_fake_tree(httpd_dir2, {
        "file2": "file2 content",
    })

    cert_dir = pathlib.Path(__file__).parent.parent / "data/certs"
    cacertfile1 = cert_dir / "cert1.pem"
    keyfile1 = cert_dir / "key1.pem"
    cacertfile2 = cert_dir / "cert2.pem"
    keyfile2 = cert_dir / "key2.pem"

    with https_serve_directory(httpd_dir1, cacertfile1, keyfile1) as httpd1:
        with https_serve_directory(httpd_dir2, cacertfile2, keyfile2) as httpd2:
            curl_config = tmp_path / "config.txt"
            # note that the "next" in there is critcial
            curl_config.write_text(textwrap.dedent(f"""\
            url = "https://localhost:{httpd1.server_port}/file1"
            cacert = {cacertfile1}
            next

            url = "https://localhost:{httpd2.server_port}/file2"
            cacert = {cacertfile2}
            """))
            print(curl_config.read_text())
            output = subprocess.check_output(
                ["curl",
                 "--config", os.fspath(curl_config),
                ],
            )
        assert output == b"file1 contentfile2 content"
