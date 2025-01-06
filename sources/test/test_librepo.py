#!/usr/bin/python3
from unittest.mock import patch

import librepo

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
def test_librepo_secrets(mocked_download_pkgs, sources_service):
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
