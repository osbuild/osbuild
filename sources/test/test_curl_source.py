#!/usr/bin/python3

import hashlib
import pathlib
import re
import shutil
import subprocess
from unittest.mock import patch

import pytest

from osbuild.testutil.net import http_serve_directory

SOURCES_NAME = "org.osbuild.curl"


def test_curl_source_not_exists(tmp_path, sources_service):
    desc = {
        "url": "http://localhost:80/a",
    }
    checksum = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
    sources_service.cache = tmp_path
    assert not sources_service.exists(checksum, desc)


def test_curl_source_exists(tmp_path, sources_service):
    desc = {
        "url": "http://localhost:80/a",
    }
    checksum = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
    sources_service.cache = tmp_path
    (sources_service.cache / checksum).touch()
    assert sources_service.exists(checksum, desc)


def test_curl_source_amend_secrets(monkeypatch, sources_service):
    desc = {
        "url": "http://localhost:80/a",
        "secrets": {
            "name": "org.osbuild.mtls",
        },
    }

    monkeypatch.setenv("OSBUILD_SOURCES_CURL_SSL_CLIENT_KEY", "key")
    monkeypatch.setenv("OSBUILD_SOURCES_CURL_SSL_CLIENT_CERT", "cert")
    checksum = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
    _, new_desc = sources_service.amend_secrets(checksum, desc)
    assert new_desc["secrets"]["ssl_client_key"] == "key"
    assert new_desc["secrets"]["ssl_client_cert"] == "cert"
    assert new_desc["secrets"]["ssl_ca_cert"] is None


def test_curl_source_amend_secrets_fail(sources_service):
    desc = {
        "url": "http://localhost:80/a",
        "secrets": {
            "name": "org.osbuild.mtls",
        },
    }
    checksum = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
    with pytest.raises(RuntimeError) as exc:
        sources_service.amend_secrets(checksum, desc)
    assert "mtls secrets required" in str(exc)


class FakeSubscriptionManager:
    def get_secrets(self, url):
        return f"secret-for-{url}"


def test_curl_source_amend_secrets_subscription_mgr(sources_service):
    desc = {
        "url": "http://localhost:80/a",
        "secrets": {
            "name": "org.osbuild.rhsm",
        },
    }

    sources_service.subscriptions = FakeSubscriptionManager()
    checksum = "sha256:1234567890123456789012345678901234567890909b14ffb032aa20fa23d9ad6"
    checksum, desc = sources_service.amend_secrets(checksum, desc)
    assert desc["secrets"] == "secret-for-http://localhost:80/a"


def test_curl_download_many_fail(sources_service):
    TEST_SOURCES = {
        "sha:1111111111111111111111111111111111111111111111111111111111111111": {
            "url": "http://localhost:9876/random-not-exists",
        },
    }
    with pytest.raises(RuntimeError) as exp:
        sources_service.fetch_all(TEST_SOURCES)
    assert str(exp.value) == 'curl: error downloading http://localhost:9876/random-not-exists: error code 7'


def make_test_sources(fake_httpd_root, port, n_files):
    """
    Create test sources for n_file. All files have the names
    0,1,2...
    and the content that matches their name (i.e. file "0" has content "0")

    Returns a sources dict that can be used as input for "fetch_all()" with
    the correct hash/urls.
    """
    fake_httpd_root.mkdir(exist_ok=True)
    sources = {}
    for i in range(n_files):
        name = f"{i}"
        sources[f"sha256:{hashlib.sha256(name.encode()).hexdigest()}"] = {
            "url": f"http://localhost:{port}/{name}",
        }
        (fake_httpd_root / name).write_text(name, encoding="utf8")

    return sources


def test_curl_download_many_with_retry(tmp_path, sources_service):
    fake_httpd_root = tmp_path / "fake-httpd-root"

    simulate_failures = 2
    with http_serve_directory(fake_httpd_root, simulate_failures=simulate_failures) as httpd:
        test_sources = make_test_sources(fake_httpd_root, httpd.server_port, 5)

        sources_service.cache = tmp_path / "curl-download-dir"
        sources_service.cache.mkdir()
        sources_service.fetch_all(test_sources)
        # we simulated N failures and we need to fetch K files
        assert httpd.reqs.count == simulate_failures + len(test_sources)
    # double downloads happend in the expected format
    for chksum in test_sources:
        assert (sources_service.cache / chksum).exists()


def test_curl_download_many_chksum_validate(tmp_path, sources_service):
    fake_httpd_root = tmp_path / "fake-httpd-root"

    with http_serve_directory(fake_httpd_root) as httpd:
        test_sources = make_test_sources(fake_httpd_root, httpd.server_port, 5)
        # "break" the hash of file "1" by replacing the content to no longer
        # match the checksum
        (fake_httpd_root / "1").write_text("hash-no-longer-matches", encoding="utf8")

        sources_service.cache = tmp_path / "curl-download-dir"
        sources_service.cache.mkdir()
        with pytest.raises(RuntimeError) as exp:
            sources_service.fetch_all(test_sources)
        assert re.search(r"checksum mismatch: sha256:.* http://localhost:.*/1", str(exp.value))


def test_curl_download_many_retries(tmp_path, sources_service):
    fake_httpd_root = tmp_path / "fake-httpd-root"

    with http_serve_directory(fake_httpd_root) as httpd:
        test_sources = make_test_sources(fake_httpd_root, httpd.server_port, 5)
        # remove all the sources
        shutil.rmtree(fake_httpd_root)

        sources_service.cache = tmp_path / "curl-download-dir"
        sources_service.cache.mkdir()
        with pytest.raises(RuntimeError) as exp:
            sources_service.fetch_all(test_sources)
        # curl will retry 10 times
        assert httpd.reqs.count == 10 * len(test_sources)
        assert "curl: error downloading http://localhost:" in str(exp.value)


class FakeCurlDownloader:
    """FakeCurlDownloader fakes what curl does

    This is useful when mocking subprocess.run() to see that curl gets
    the right arguments. It requires test sources where the filename
    matches the content of the file (e.g. filename "a", content must be "a"
    as well) so that it can generate the right hash.
    """

    def __init__(self, test_sources):
        self._test_sources = test_sources

    def faked_run(self, *args, **kwargs):
        download_dir = pathlib.Path(kwargs["cwd"])
        for chksum, desc in self._test_sources.items():
            # The filename of our test files matches their content for
            # easier testing/hashing. Alternatively we could just pass
            # a src dir in here and copy the files from src to
            # download_dir here but that would require that the files
            # always exist in the source dir (which they do right now).
            content = desc["url"].rsplit("/", 1)[1]
            (download_dir / chksum).write_text(content, encoding="utf8")
        return subprocess.CompletedProcess(args, 0)


@pytest.mark.parametrize("with_proxy", [True, False])
@patch("subprocess.run")
def test_curl_download_proxy(mocked_run, tmp_path, monkeypatch, sources_service, with_proxy):
    test_sources = make_test_sources(tmp_path, 80, 2)
    fake_curl_downloader = FakeCurlDownloader(test_sources)
    mocked_run.side_effect = fake_curl_downloader.faked_run

    if with_proxy:
        monkeypatch.setenv("OSBUILD_SOURCES_CURL_PROXY", "http://my-proxy")
    sources_service.cache = tmp_path / "curl-cache"
    sources_service.cache.mkdir()
    sources_service.fetch_all(test_sources)
    for call_args in mocked_run.call_args_list:
        args, _kwargs = call_args
        if with_proxy:
            idx = args[0].index("--proxy")
            assert args[0][idx:idx + 2] == ["--proxy", "http://my-proxy"]
        else:
            assert "--proxy" not in args[0]


@patch("subprocess.run")
def test_curl_user_agent(mocked_run, tmp_path, sources_service):
    test_sources = make_test_sources(tmp_path, 80, 2,)
    fake_curl_downloader = FakeCurlDownloader(test_sources)
    mocked_run.side_effect = fake_curl_downloader.faked_run

    sources_service.cache = tmp_path / "curl-cache"
    sources_service.cache.mkdir()
    sources_service.fetch_all(test_sources)

    for call_args in mocked_run.call_args_list:
        args, _kwargs = call_args
        idx = args[0].index("--header")
        assert "User-Agent: osbuild" in args[0][idx + 1]
        assert "https://osbuild.org/" in args[0][idx + 1]
