#
# Tests for the `osbuild.util.rhsm` module.
#

# NB: Some fixtures defined in this file are patching certain stdlib function,
# which means that pylint will complain about them. We ignore these warnings.
# Moreover, it is sometimes necessary to access protected methods in the tests.
# pylint: disable=unused-argument,redefined-outer-name,protected-access

import contextlib
import os
from io import StringIO
from unittest.mock import patch

import pytest

from osbuild.testutil import make_fake_tree
from osbuild.util.rhsm import Subscriptions

# Sample repo file content for testing
REPO_FILE = """[jpp]
name = Red Hat JBoss Portal
baseurl = https://cdn.redhat.com/1.0/$basearch/os
enabled = 0
gpgcheck = 1
gpgkey = file://
sslverify = 1
sslcacert = /etc/rhsm/ca/redhat-uep.pem
sslclientkey = /etc/pki/entitlement/1-key.pem
sslclientcert = /etc/pki/entitlement/1.pem
metadata_expire = 86400
enabled_metadata = 0

[jws]
name = Red Hat JBoss Web
baseurl = https://cdn.redhat.com/$releasever/jws/1.0/$basearch/os
enabled = 0
gpgcheck = 1
gpgkey = file://
sslverify = 1
sslcacert = /etc/rhsm/ca/redhat-uep.pem
sslclientkey = /etc/pki/entitlement/2-key.pem
sslclientcert = /etc/pki/entitlement/2.pem
metadata_expire = 86400
enabled_metadata = 0
"""

# Repo file without sslcacert (simulates rhc/Insights registration)
REPO_FILE_NO_SSLCACERT = """[rhel-baseos]
name = Red Hat Enterprise Linux BaseOS
baseurl = https://cdn.redhat.com/$releasever/baseos/$basearch/os
enabled = 1
gpgcheck = 1
gpgkey = file://
sslverify = 1
sslclientkey = /etc/pki/entitlement/123-key.pem
sslclientcert = /etc/pki/entitlement/123.pem
metadata_expire = 86400
enabled_metadata = 0
"""


@contextlib.contextmanager
def patched_path_exists(fake_root):
    """
    Context manager that patches os.path.exists to redirect /run and /etc paths
    to the fake root directory.
    """
    fake_root_str = os.fspath(fake_root)
    original_exists = os.path.exists

    def check_exists(path):
        if path.startswith(("/run", "/etc")):
            fake_path = os.path.join(fake_root_str, path.lstrip("/"))
            return original_exists(fake_path)
        return original_exists(path)

    with patch.object(os.path, 'exists', side_effect=check_exists):
        yield fake_root


@pytest.fixture
def mock_subscribed_system(tmp_path):
    """Set up a mock subscribed system with redhat.repo and entitlement certs."""
    make_fake_tree(tmp_path, {
        "etc/rhsm/ca/redhat-uep.pem": "FAKE CA CERT",
        "etc/pki/entitlement/1234567890-key.pem": "FAKE KEY",
        "etc/pki/entitlement/1234567890.pem": "FAKE CERT",
        "etc/yum.repos.d/redhat.repo": REPO_FILE,
    })
    return tmp_path


@pytest.fixture
def mock_empty_system(tmp_path):
    """Set up an empty system with os.path.exists patched."""
    with patched_path_exists(tmp_path) as fake_root:
        yield fake_root


@pytest.fixture
def mock_container_unsubscribed(tmp_path):
    """Set up a mock container environment on an unsubscribed host with os.path.exists patched."""
    make_fake_tree(tmp_path, {
        "run/.containerenv": "",
    })
    with patched_path_exists(tmp_path) as fake_root:
        yield fake_root


@pytest.fixture
def mock_container_subscribed(tmp_path):
    """Set up a mock container environment on a subscribed host with os.path.exists patched."""
    make_fake_tree(tmp_path, {
        "run/.containerenv": "",
        "run/secrets/rhsm/ca/redhat-uep.pem": "FAKE CA CERT",
        "run/secrets/etc-pki-entitlement/9876543210-key.pem": "FAKE KEY",
        "run/secrets/etc-pki-entitlement/9876543210.pem": "FAKE CERT",
        "run/secrets/redhat.repo": REPO_FILE,
    })
    with patched_path_exists(tmp_path) as fake_root:
        yield fake_root


@pytest.fixture
def mock_consumer_certs(tmp_path):
    """Set up mock consumer identity certificates with os.path.exists patched."""
    make_fake_tree(tmp_path, {
        "etc/pki/consumer/key.pem": "FAKE CONSUMER KEY",
        "etc/pki/consumer/cert.pem": "FAKE CONSUMER CERT",
    })
    with patched_path_exists(tmp_path) as fake_root:
        yield fake_root


class TestContainerDetection:
    """Tests for container detection and RHSM secrets paths."""

    def test_not_in_container(self, mock_empty_system):
        assert not Subscriptions.is_container_with_rhsm_secrets()

    def test_in_container_without_secrets(self, mock_container_unsubscribed):
        assert not Subscriptions.is_container_with_rhsm_secrets()

    def test_in_container_with_secrets(self, mock_container_subscribed):
        assert Subscriptions.is_container_with_rhsm_secrets()
        subscriptions = Subscriptions(repositories=None)
        assert subscriptions.DEFAULT_SSL_CA_CERT == "/run/secrets/rhsm/ca/redhat-uep.pem"
        assert subscriptions.DEFAULT_ENTITLEMENT_DIR == "/run/secrets/etc-pki-entitlement"
        assert subscriptions.DEFAULT_REPO_FILE == "/run/secrets/redhat.repo"


class TestSubscribedSystem:
    """Tests for regular subscribed RHEL systems."""

    def test_parse_repo_file(self):
        subscriptions = Subscriptions.parse_repo_file(StringIO(REPO_FILE))
        assert subscriptions.repositories is not None
        assert "jpp" in subscriptions.repositories
        assert "jws" in subscriptions.repositories
        jpp = subscriptions.repositories["jpp"]
        assert jpp["sslcacert"] == "/etc/rhsm/ca/redhat-uep.pem"
        assert jpp["sslclientkey"] == "/etc/pki/entitlement/1-key.pem"
        assert jpp["sslclientcert"] == "/etc/pki/entitlement/1.pem"

    @pytest.mark.parametrize("url,should_succeed,key", [
        ("https://cdn.redhat.com/8/jws/1.0/risc_v/os/Packages/fishy-fish-1-1.el8.risc_v.rpm", True, "2"),
        ("https://cdn.redhat.com/8/jws/1.0/os/Packages/fishy-fish-1-1.el8.risc_v.rpm", False, ""),
        ("https://cdn.redhat.com/1.0/x86_64/os/Packages/aaa.rpm", True, "1"),
        ("https://some.other.host/path/to/rpm.rpm", False, ""),
    ])
    def test_get_secrets_url_matching(self, url, should_succeed, key):
        subscriptions = Subscriptions.parse_repo_file(StringIO(REPO_FILE))
        if not should_succeed:
            with pytest.raises(RuntimeError, match="no RHSM secret associated"):
                subscriptions.get_secrets([url])
        else:
            secrets = subscriptions.get_secrets([url])
            assert secrets["ssl_ca_cert"] == "/etc/rhsm/ca/redhat-uep.pem"
            assert secrets["ssl_client_key"] == f"/etc/pki/entitlement/{key}-key.pem"
            assert secrets["ssl_client_cert"] == f"/etc/pki/entitlement/{key}.pem"


class TestUnsubscribedSystem:
    """Tests for unsubscribed systems."""

    @pytest.mark.parametrize("repositories", [None, {}])
    def test_no_repositories_no_secrets(self, repositories):
        subscriptions = Subscriptions(repositories=repositories)
        with pytest.raises(RuntimeError, match="no RHSM secret associated"):
            subscriptions.get_secrets(["https://cdn.redhat.com/any/url"])


class TestRhcSubscribedSystem:
    """Tests for systems subscribed via rhc/Insights (missing sslcacert in repo)."""

    def test_missing_sslcacert_uses_default_ca(self):
        subscriptions = Subscriptions.parse_repo_file(StringIO(REPO_FILE_NO_SSLCACERT))
        # verify that the repo file was parsed correctly
        assert subscriptions.repositories is not None
        assert "rhel-baseos" in subscriptions.repositories
        assert subscriptions.repositories["rhel-baseos"]["sslcacert"] == Subscriptions.DEFAULT_SSL_CA_CERT

        # verify that the secrets are retrieved correctly
        secrets = subscriptions.get_secrets(["https://cdn.redhat.com/9/baseos/x86_64/os/Packages/test.rpm"])
        assert secrets["ssl_ca_cert"] == Subscriptions.DEFAULT_SSL_CA_CERT
        assert secrets["ssl_client_key"] == "/etc/pki/entitlement/123-key.pem"
        assert secrets["ssl_client_cert"] == "/etc/pki/entitlement/123.pem"


class TestConsumerSecrets:
    """Tests for consumer identity certificates (used by ostree)."""

    def test_get_consumer_secrets_success(self, mock_consumer_certs):
        secrets = Subscriptions.get_consumer_secrets()
        assert secrets["consumer_key"] == "/etc/pki/consumer/key.pem"
        assert secrets["consumer_cert"] == "/etc/pki/consumer/cert.pem"

    def test_get_consumer_secrets_missing_raises(self, mock_empty_system):
        with pytest.raises(RuntimeError, match="consumer key and cert not found"):
            Subscriptions.get_consumer_secrets()


class TestFallbackSecrets:
    """Tests for fallback RHSM secrets from entitlement directory."""

    def test_get_fallback_no_certs_raises(self, tmp_path):
        subscriptions = Subscriptions(repositories=None)
        subscriptions.DEFAULT_ENTITLEMENT_DIR = os.fspath(tmp_path)
        with pytest.raises(RuntimeError, match="no matching rhsm key and cert"):
            subscriptions.get_fallback_rhsm_secrets()

    def test_get_fallback_finds_matching_certs(self, tmp_path):
        subscriptions = Subscriptions(repositories=None)
        subscriptions.DEFAULT_ENTITLEMENT_DIR = os.fspath(tmp_path)
        subscriptions.DEFAULT_SSL_CA_CERT = "/etc/rhsm/ca/redhat-uep.pem"

        # Create matching key and cert pair
        make_fake_tree(tmp_path, {
            "1234567890-key.pem": "FAKE KEY",
            "1234567890.pem": "FAKE CERT",
        })

        # The method always raises, but secrets are set before the raise
        with pytest.raises(RuntimeError, match="no matching rhsm key and cert"):
            subscriptions.get_fallback_rhsm_secrets()

        # Verify secrets were set despite the exception
        assert subscriptions.secrets is not None
        assert subscriptions.secrets["ssl_ca_cert"] == "/etc/rhsm/ca/redhat-uep.pem"
        assert subscriptions.secrets["ssl_client_key"] == os.path.join(tmp_path, "1234567890-key.pem")
        assert subscriptions.secrets["ssl_client_cert"] == os.path.join(tmp_path, "1234567890.pem")


class TestUrlMatching:
    """Tests for URL pattern matching from baseurls."""

    @pytest.mark.parametrize("baseurl,test_url,should_match", [
        pytest.param(
            "https://cdn.redhat.com/1.0/$basearch/os",
            "https://cdn.redhat.com/1.0/x86_64/os/Packages/test.rpm",
            True,
            id="basearch",
        ),
        pytest.param(
            "https://cdn.redhat.com/$releasever/repo/$basearch/os",
            "https://cdn.redhat.com/9/repo/x86_64/os/test.rpm",
            True,
            id="releasever and basearch",
        ),
        pytest.param(
            "https://cdn.redhat.com/$releasever/repo/$basearch/os",
            "https://cdn.redhat.com/9/different/x86_64/os/test.rpm",
            False,
            id="wrong path structure",
        ),
        pytest.param(
            "https://cdn.redhat.com/1.0/$basearch/os",
            "https://other.host.com/1.0/x86_64/os/test.rpm",
            False,
            id="different host",
        ),
        pytest.param(
            "https://cdn.redhat.com/$uuid/content",
            "https://cdn.redhat.com/abc-123-def/content/test.rpm",
            True,
            id="UUID variable",
        ),
    ])
    def test_process_baseurl_matching(self, baseurl, test_url, should_match):
        pattern = Subscriptions._process_baseurl(baseurl)
        result = pattern.match(test_url) is not None
        assert result == should_match


class TestIntegration:
    """Integration-style tests using full mock filesystem setups."""

    def test_full_flow_subscribed_system(self, mock_subscribed_system):
        repo_path = mock_subscribed_system / "etc/yum.repos.d/redhat.repo"

        with open(os.fspath(repo_path), "r", encoding="utf8") as fp:
            subscriptions = Subscriptions.parse_repo_file(fp)

        # Test URL matching and secret retrieval
        url = "https://cdn.redhat.com/1.0/x86_64/os/Packages/test.rpm"
        secrets = subscriptions.get_secrets([url])

        assert "ssl_ca_cert" in secrets
        assert "ssl_client_key" in secrets
        assert "ssl_client_cert" in secrets

    def test_fallback_used_when_no_url_match(self):
        # Create minimal repo with unrelated baseurl
        repo_content = """[unrelated]
name = Unrelated Repo
baseurl = https://other.server/path
sslcacert = /etc/rhsm/ca/redhat-uep.pem
sslclientkey = /etc/pki/entitlement/999-key.pem
sslclientcert = /etc/pki/entitlement/999.pem
"""
        subscriptions = Subscriptions.parse_repo_file(StringIO(repo_content))

        # Set up fallback
        subscriptions.secrets = {
            "ssl_ca_cert": "/fallback/ca.pem",
            "ssl_client_key": "/fallback/key.pem",
            "ssl_client_cert": "/fallback/cert.pem"
        }

        # URL doesn't match unrelated repo, should use fallback
        url = "https://cdn.redhat.com/some/path/test.rpm"
        secrets = subscriptions.get_secrets([url])

        assert secrets["ssl_ca_cert"] == "/fallback/ca.pem"
        assert secrets["ssl_client_key"] == "/fallback/key.pem"
        assert secrets["ssl_client_cert"] == "/fallback/cert.pem"
