#!/usr/bin/python3

import contextlib
import os
import pathlib
import socket
import tempfile

import pytest

SOURCES_NAME = "org.osbuild.curl"


def test_curl_source_not_exists(sources_module):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    curl_source = sources_module.CurlSource.from_args(["--service-fd", str(sock.fileno())])
    tmpdir = tempfile.TemporaryDirectory()
    curl_source.cache = tmpdir.name
    desc = {
        "url": "http://localhost:80/a",
    }
    checksum = "sha256:1234567890123456789012345678901234567890909b14ffb032aa20fa23d9ad6"
    assert not curl_source.exists(checksum, desc)


def test_curl_source_exists(sources_module):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    curl_source = sources_module.CurlSource.from_args(["--service-fd", str(sock.fileno())])
    tmpdir = tempfile.TemporaryDirectory()
    curl_source.cache = tmpdir.name
    desc = {
        "url": "http://localhost:80/a",
    }
    checksum = "sha256:1234567890123456789012345678901234567890909b14ffb032aa20fa23d9ad6"
    pathlib.Path(os.path.join(tmpdir.name, checksum)).touch()
    assert curl_source.exists(checksum, desc)


def test_curl_source_amend_secrets(sources_module):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    curl_source = sources_module.CurlSource.from_args(["--service-fd", str(sock.fileno())])
    tmpdir = tempfile.TemporaryDirectory()
    curl_source.cache = tmpdir.name
    desc = {
        "url": "http://localhost:80/a",
        "secrets": {
            "name": "org.osbuild.mtls",
        },
    }

    with contextlib.ExitStack() as cm:
        os.environ["OSBUILD_SOURCES_CURL_SSL_CLIENT_KEY"] = "key"
        os.environ["OSBUILD_SOURCES_CURL_SSL_CLIENT_CERT"] = "cert"

        def cb():
            del os.environ["OSBUILD_SOURCES_CURL_SSL_CLIENT_KEY"]
            del os.environ["OSBUILD_SOURCES_CURL_SSL_CLIENT_CERT"]
        cm.callback(cb)
        checksum = "sha256:1234567890123456789012345678901234567890909b14ffb032aa20fa23d9ad6"
        pathlib.Path(os.path.join(tmpdir.name, checksum)).touch()
        new_desc = curl_source.amend_secrets(checksum, desc)
        assert new_desc[1]["secrets"]["ssl_client_key"] == "key"
        assert new_desc[1]["secrets"]["ssl_client_cert"] == "cert"
        assert new_desc[1]["secrets"]["ssl_ca_cert"] is None


def test_curl_source_amend_secrets_fail(sources_module):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    curl_source = sources_module.CurlSource.from_args(["--service-fd", str(sock.fileno())])
    tmpdir = tempfile.TemporaryDirectory()
    curl_source.cache = tmpdir.name
    desc = {
        "url": "http://localhost:80/a",
        "secrets": {
            "name": "org.osbuild.mtls",
        },
    }
    checksum = "sha256:1234567890123456789012345678901234567890909b14ffb032aa20fa23d9ad6"
    pathlib.Path(os.path.join(tmpdir.name, checksum)).touch()
    with pytest.raises(RuntimeError) as exc:
        curl_source.amend_secrets(checksum, desc)
    assert "mtls secrets required" in str(exc)
