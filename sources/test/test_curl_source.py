#!/usr/bin/python3

import hashlib
import platform
import re
import shutil
import textwrap

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


def test_curl_user_agent(tmp_path, sources_module):
    config_path = tmp_path / "curl-config.txt"
    test_sources = make_test_sources(tmp_path, 80, 2)

    sources_module.gen_curl_download_config(config_path, test_sources.items())
    assert config_path.exists()
    assert 'user-agent = "osbuild (Linux.x86_64; https://osbuild.org/)"' in config_path.read_text()


@pytest.mark.parametrize("with_proxy", [True, False])
def test_curl_download_proxy(tmp_path, monkeypatch, sources_module, with_proxy):
    config_path = tmp_path / "curl-config.txt"
    test_sources = make_test_sources(tmp_path, 80, 2)

    if with_proxy:
        monkeypatch.setenv("OSBUILD_SOURCES_CURL_PROXY", "http://my-proxy")
    sources_module.gen_curl_download_config(config_path, test_sources.items())
    assert config_path.exists()
    if with_proxy:
        assert 'proxy = "http://my-proxy"\n' in config_path.read_text()
    else:
        assert "proxy" not in config_path.read_text()


TEST_SOURCE_PAIRS_GEN_DOWNLOAD_CONFIG = [
    (
        # sha256("0")
        "sha256:5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9",
        {
            "url": "http://example.com/file/0",
        },
    ), (
        # sha256("1")
        "sha256:6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
        {
            "url": "http://example.com/file/1",
            "insecure": True,
        },
    ), (
        # sha256("2")
        "sha256:d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
        {
            "url": "http://example.com/file/2",
            "secrets": {
                "ssl_ca_cert": "some-ssl_ca_cert",
            },
        },
    ), (
        # sha256("3")
        "sha256:4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
        {
            "url": "http://example.com/file/3",
            "secrets": {
                "ssl_client_cert": "some-ssl_client_cert",
                "ssl_client_key": "some-ssl_client_key",
            },
        },
    ),
]


def test_curl_gen_download_config(tmp_path, sources_module):
    config_path = tmp_path / "curl-config.txt"
    sources_module.gen_curl_download_config(config_path, TEST_SOURCE_PAIRS_GEN_DOWNLOAD_CONFIG)

    assert config_path.exists()
    assert config_path.read_text(encoding="utf8") == textwrap.dedent(f"""\
    user-agent = "osbuild (Linux.{platform.machine()}; https://osbuild.org/)"
    silent
    speed-limit = 1000
    connect-timeout = 30
    fail
    location

    url = "http://example.com/file/0"
    output = "sha256:5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9"
    no-insecure

    url = "http://example.com/file/1"
    output = "sha256:6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b"
    insecure

    url = "http://example.com/file/2"
    output = "sha256:d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35"
    cacert = "some-ssl_ca_cert"
    no-insecure

    url = "http://example.com/file/3"
    output = "sha256:4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce"
    cert = "some-ssl_client_cert"
    key = "some-ssl_client_key"
    no-insecure

    """)
