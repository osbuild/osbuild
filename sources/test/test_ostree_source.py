#!/usr/bin/python3

import os
import pathlib
import tempfile

import pytest

from osbuild.testutil import has_executable
from osbuild.testutil.net import http_serve_directory, https_serve_directory
from osbuild.util import ostree

SOURCES_NAME = "org.osbuild.ostree"


@pytest.mark.skipif(not has_executable("ostree"), reason="need ostree")
def test_ostree_source_not_exists(tmp_path, sources_service):
    checksum = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
    sources_service.setup({"cache": tmp_path, "options": {}})
    assert not sources_service.exists(checksum, None)


@pytest.mark.skipif(not has_executable("ostree"), reason="need ostree")
def test_ostree_source_exists(tmp_path, sources_service):
    sources_service.setup({"cache": tmp_path, "options": {}})
    root = tmp_path / "org.osbuild.ostree" / "repo"
    commit = make_repo(root)
    assert sources_service.exists("sha256:" + commit, None)


def make_test_sources(proto, port, fake_commit, subpaths, **secrets):
    sources = {
        fake_commit: {
            "remote": {
                "url": f"{proto}://localhost:{port}",
                "subpaths": subpaths,
            }
        }
    }
    if secrets:
        sources[fake_commit]["remote"]["secrets"] = secrets
    return sources


def make_repo(root):
    with tempfile.TemporaryDirectory() as empty_tmpdir:
        ostree.cli("init", "--mode=archive", f"--repo={root}")
        os.mknod(os.path.join(empty_tmpdir, "a.txt"))
        os.mknod(os.path.join(empty_tmpdir, "b.txt"))
        return ostree.cli("commit", f"--repo={root}", "--orphan", empty_tmpdir).stdout.rstrip()


@pytest.mark.skipif(not has_executable("ostree"), reason="need ostree")
def test_ostree_pull_plain(tmp_path, sources_service):
    fake_httpd_root = tmp_path / "fake-httpd-root"
    fake_httpd_root.mkdir(exist_ok=True)
    fake_commit = make_repo(fake_httpd_root)

    with http_serve_directory(fake_httpd_root) as httpd:
        test_sources = make_test_sources("http", httpd.server_port, fake_commit, [])
        sources_service.setup({"cache": tmp_path, "options": {}})
        sources_service.fetch_all(test_sources)
        assert sources_service.exists("sha256:" + fake_commit, None)


@pytest.mark.skipif(not has_executable("ostree"), reason="need ostree")
def test_ostree_pull_subtree(tmp_path, sources_service, capsys):
    fake_httpd_root = tmp_path / "fake-httpd-root"
    fake_httpd_root.mkdir(exist_ok=True)
    fake_commit = make_repo(fake_httpd_root)

    with http_serve_directory(fake_httpd_root) as httpd:
        test_sources = make_test_sources("http", httpd.server_port, fake_commit, ["/b.txt"])
        sources_service.setup({"cache": tmp_path, "options": {}})
        sources_service.fetch_all(test_sources)
        assert sources_service.exists("sha256:" + fake_commit, None)

    assert "--subpath=/b.txt" in capsys.readouterr().err


@pytest.mark.skipif(not has_executable("ostree"), reason="need ostree")
def test_ostree_pull_plain_mtls(tmp_path, sources_service, monkeypatch):
    fake_httpd_root = tmp_path / "fake-httpd-root"
    fake_httpd_root.mkdir(exist_ok=True)
    fake_commit = make_repo(fake_httpd_root)

    cert_dir = pathlib.Path(__file__).parent.parent.parent / "test" / "data" / "certs"
    cert1 = cert_dir / "cert1.pem"
    assert cert1.exists()
    key1 = cert_dir / "key1.pem"
    assert key1.exists()

    with https_serve_directory(fake_httpd_root, cert1, key1) as httpd:
        monkeypatch.setenv("OSBUILD_SOURCES_OSTREE_INSECURE", "1")
        test_sources = make_test_sources("https", httpd.server_port, fake_commit, [], name="org.osbuild.mtls")
        sources_service.setup({"cache": tmp_path, "options": {}})
        sources_service.fetch_all(test_sources)
        assert sources_service.exists("sha256:" + fake_commit, None)
