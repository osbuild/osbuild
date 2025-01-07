#!/usr/bin/python3
from unittest.mock import patch

try:
    import librepo
except ImportError:
    import pytest
    pytest.skip("need librepo to run this test", allow_module_level=True)
import pytest

from osbuild import testutil

SOURCES_NAME = "org.osbuild.librepo"


@patch("librepo.download_packages")
def test_librepo_download_mocked(mocked_download_pkgs, sources_service):
    TEST_SOURCES = {
        "sha256:1111111111111111111111111111111111111111111111111111111111111111": {
            "path": "Packages/a/a",
            "mirror": "mirror_id",
        },
        "sha256:2111111111111111111111111111111111111111111111111111111111111111": {
            "path": "Packages/b/b",
            "mirror": "mirror_id2",
        },
    }
    sources_service.options = {
        "mirrors": {
            "mirror_id": {
                "url": "http://example.com/mirrorlist",
                "type": "mirrorlist",
            },
            "mirror_id2": {
                "url": "http://example.com/mirrorlist2",
                "type": "mirrorlist",
            }
        }
    }
    sources_service.cache = "cachedir"
    sources_service.fetch_all(TEST_SOURCES)
    # we expect one download call per mirror
    assert len(mocked_download_pkgs.call_args_list) == 2
    # extract the list of packages to download (all_calls->call()->args->args[0])
    download_pkgs = mocked_download_pkgs.call_args_list[0][0][0]
    assert download_pkgs[0].checksum == "1111111111111111111111111111111111111111111111111111111111111111"
    assert download_pkgs[0].checksum_type == librepo.SHA256
    assert download_pkgs[0].relative_url == "Packages/a/a"
    assert download_pkgs[0].dest == "cachedir/sha256:1111111111111111111111111111111111111111111111111111111111111111"
    assert download_pkgs[0].handle.mirrorlisturl == "http://example.com/mirrorlist"
    # and now the second call
    download_pkgs = mocked_download_pkgs.call_args_list[1][0][0]
    assert download_pkgs[0].checksum == "2111111111111111111111111111111111111111111111111111111111111111"
    assert download_pkgs[0].checksum_type == librepo.SHA256
    assert download_pkgs[0].relative_url == "Packages/b/b"
    assert download_pkgs[0].dest == "cachedir/sha256:2111111111111111111111111111111111111111111111111111111111111111"
    assert download_pkgs[0].handle.mirrorlisturl == "http://example.com/mirrorlist2"


class FakeSubscriptionManager:
    def __init__(self):
        self.get_secrets_calls = []

    def get_secrets(self, url):
        self.get_secrets_calls.append(url)
        return {
            "ssl_ca_cert": "rhsm-ca-cert",
            "ssl_client_cert": "rhsm-client-cert",
            "ssl_client_key": "rhsm-client-key",
        }


@patch("librepo.download_packages")
def test_librepo_secrets_rhsm(mocked_download_pkgs, sources_service):
    TEST_SOURCES = {
        "sha256:1111111111111111111111111111111111111111111111111111111111111111": {
            "path": "Packages/a/a",
            "mirror": "mirror_id",
        }
    }
    sources_service.options = {
        "mirrors": {
            "mirror_id": {
                "url": "http://example.com/mirrorlist",
                "type": "mirrorlist",
                "secrets": {
                    "name": "org.osbuild.rhsm",
                }
            }
        }
    }
    sources_service.cache = "cachedir"
    sources_service.subscriptions = FakeSubscriptionManager()
    sources_service.fetch_all(TEST_SOURCES)
    assert len(mocked_download_pkgs.call_args_list) == 1
    # extract the list of packages to download (all_calls->call()->args->args[0])
    download_pkgs = mocked_download_pkgs.call_args_list[0][0][0]
    assert download_pkgs[0].checksum == "1111111111111111111111111111111111111111111111111111111111111111"
    assert download_pkgs[0].handle.sslclientkey == "rhsm-client-key"
    assert download_pkgs[0].handle.sslclientcert == "rhsm-client-cert"
    assert download_pkgs[0].handle.sslcacert == "rhsm-ca-cert"
    # double check that get_secrets() was called
    assert sources_service.subscriptions.get_secrets_calls == ["http://example.com/mirrorlist"]


@patch("librepo.download_packages")
def test_librepo_secrets_mtls(mocked_download_pkgs, sources_service, monkeypatch):
    TEST_SOURCES = {
        "sha256:1111111111111111111111111111111111111111111111111111111111111111": {
            "path": "Packages/a/a",
            "mirror": "mirror_id",
        }
    }
    sources_service.options = {
        "mirrors": {
            "mirror_id": {
                "url": "http://example.com/mirrorlist",
                "type": "mirrorlist",
                "secrets": {
                    "name": "org.osbuild.mtls",
                }
            }
        }
    }
    monkeypatch.setenv("OSBUILD_SOURCES_CURL_SSL_CLIENT_KEY", "mtls-client-key")
    monkeypatch.setenv("OSBUILD_SOURCES_CURL_SSL_CLIENT_CERT", "mtls-client-cert")
    monkeypatch.setenv("OSBUILD_SOURCES_CURL_SSL_CA_CERT", "mtls-ca-cert")

    sources_service.cache = "cachedir"
    sources_service.fetch_all(TEST_SOURCES)
    assert len(mocked_download_pkgs.call_args_list) == 1
    # extract the list of packages to download (all_calls->call()->args->args[0])
    download_pkgs = mocked_download_pkgs.call_args_list[0][0][0]
    assert download_pkgs[0].checksum == "1111111111111111111111111111111111111111111111111111111111111111"
    assert download_pkgs[0].handle.sslclientkey == "mtls-client-key"
    assert download_pkgs[0].handle.sslclientcert == "mtls-client-cert"
    assert download_pkgs[0].handle.sslcacert == "mtls-ca-cert"


@pytest.mark.parametrize("test_mirrors,expected_err", [
    # bad
    (
        # only hashes supported for mirror_ids
        {"bad_mirror_id": {"url": "http://example.com", "type": "mirrorlist"}},
        "'bad_mirror_id' does not match any of the regexes: '^[0-9a-f]+$'",
    ),
    (
        {"0123456789abcdef": {"type": "mirrorlist"}},
        "'url' is a required property",
    ),
    (
        {"0123456789abcdef": {"url": "http://example.com"}},
        "'type' is a required property",
    ),
    (
        {"0123456789abcdef": {"url": "http://example.com", "type": "bad_type"}},
        "'bad_type' is not one of ['mirrorlist', 'metalink', 'baseurl']",
    ),
    # good
    (
        {}, "",
    ),
    (
        {"0123": {"url": "http://example.com", "type": "mirrorlist"}}, "",
    ),
    (
        {"0123": {"url": "http://example.com", "type": "metalink"}}, "",
    ),
    (
        {"0123": {"url": "http://example.com", "type": "baseurl"}}, "",
    )
])
def test_schema_validation(sources_schema, test_mirrors, expected_err):
    test_input = {
        "items": {
            "sha256:2111111111111111111111111111111111111111111111111111111111111111": {
                "path": "Packages/b/b",
                "mirror": "mirror_id",
            },
        },
        "options": {
            "mirrors": test_mirrors,
        }
    }
    res = sources_schema.validate(test_input)
    if expected_err == "":
        assert res.valid
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err)
