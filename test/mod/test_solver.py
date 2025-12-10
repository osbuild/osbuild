"""
Tests for the osbuild.solver module.

This module tests the SolverBase class and its RHSM subscription handling logic.
"""
from unittest.mock import MagicMock, call, patch

import pytest

from osbuild.solver import SolverBase
from osbuild.solver.exceptions import InvalidRequestError, NoRHSMSubscriptionsError
from osbuild.solver.model import Repository
from osbuild.solver.request import SolverConfig


class DummySolver(SolverBase):
    """Concrete implementation of SolverBase for testing."""
    SOLVER_NAME = "dummy"

    def dump(self):
        pass

    def depsolve(self, args):
        pass

    def search(self, args):
        pass


@pytest.mark.parametrize("repos,use_root_dir", [
    pytest.param([], True, id="empty-repos"),
    pytest.param(None, True, id="none-repos"),
    pytest.param(
        [Repository.from_request(repo_id="test", baseurl=["http://example.com"])],
        False,
        id="no-rhsm-repo-simple",
    ),
    pytest.param(
        [
            Repository.from_request(
                repo_id="test",
                baseurl=["http://example.com", "http://example.com/2"],
                metalink="http://example.com/metalink",
                mirrorlist="http://example.com/mirrorlist",
            ),
            Repository.from_request(
                repo_id="test2",
                baseurl=["http://example.com/3", "http://example.com/4"],
                metalink="http://example.com/metalink/2",
                mirrorlist="http://example.com/mirrorlist/2",
            ),
        ],
        False,
        id="no-rhsm-repo-multiple",
    ),
])
def test_no_subscription_lookup_when_not_needed(tmp_path, repos, use_root_dir):
    """
    Test that Subscriptions.from_host_system and Subscriptions.get_secrets
    are not called when no repo has rhsm=True.
    """
    config_kwargs = {
        "arch": "x86_64",
        "releasever": "9",
        "cachedir": str(tmp_path / "cache"),
        "repos": repos,
    }
    if use_root_dir:
        config_kwargs["root_dir"] = "/"
    config = SolverConfig(**config_kwargs)

    with patch("osbuild.solver.Subscriptions") as mock_subscriptions:
        solver = DummySolver(config, persistdir=tmp_path / "persist")
        mock_subscriptions.from_host_system.assert_not_called()
        mock_subscriptions.get_secrets.assert_not_called()
        assert len(solver.repo_ids_with_rhsm) == 0


@pytest.mark.parametrize("repo_kwargs,expected_urls", [
    pytest.param(
        {"baseurl": ["https://cdn.redhat.com/repo"]},
        ["https://cdn.redhat.com/repo"],
        id="baseurl",
    ),
    pytest.param(
        {"baseurl": ["https://cdn.redhat.com/repo1", "https://cdn.redhat.com/repo2"]},
        ["https://cdn.redhat.com/repo1", "https://cdn.redhat.com/repo2"],
        id="multiple-baseurls",
    ),
    pytest.param(
        {"metalink": "https://cdn.redhat.com/metalink"},
        ["https://cdn.redhat.com/metalink"],
        id="metalink",
    ),
    pytest.param(
        {"mirrorlist": "https://cdn.redhat.com/mirrorlist"},
        ["https://cdn.redhat.com/mirrorlist"],
        id="mirrorlist",
    ),
    pytest.param(
        {
            "baseurl": ["https://cdn.redhat.com/repo1", "https://cdn.redhat.com/repo2"],
            "metalink": "https://cdn.redhat.com/metalink",
            "mirrorlist": "https://cdn.redhat.com/mirrorlist",
        },
        [
            "https://cdn.redhat.com/repo1",
            "https://cdn.redhat.com/repo2",
            "https://cdn.redhat.com/metalink",
            "https://cdn.redhat.com/mirrorlist",
        ],
        id="all-url-types",
    ),
])
def test_rhsm_url_collection(tmp_path, repo_kwargs, expected_urls):
    """Test that the correct URLs are passed to get_secrets for various repo configurations."""
    repos = [
        Repository.from_request(repo_id="rhel", rhsm=True, **repo_kwargs),
        # A non-RHSM repo, which should not be handled by the RHSM logic
        Repository.from_request(repo_id="epel", baseurl=["https://example.com/epel"]),
    ]
    config = SolverConfig(
        arch="x86_64",
        releasever="9",
        cachedir=str(tmp_path / "cache"),
        repos=repos,
    )

    mock_secrets = {
        "ssl_ca_cert": "/etc/rhsm/ca/redhat-uep.pem",
        "ssl_client_key": "/etc/pki/entitlement/123-key.pem",
        "ssl_client_cert": "/etc/pki/entitlement/123.pem",
    }
    mock_subscriptions_instance = MagicMock()
    mock_subscriptions_instance.get_secrets.return_value = mock_secrets

    with patch("osbuild.solver.Subscriptions") as mock_subscriptions:
        mock_subscriptions.from_host_system.return_value = mock_subscriptions_instance
        solver = DummySolver(config, persistdir=tmp_path / "persist")

        mock_subscriptions.from_host_system.assert_called_once()
        mock_subscriptions_instance.get_secrets.assert_called_once_with(expected_urls)
        assert solver.repo_ids_with_rhsm == {"rhel"}

        assert repos[0].sslcacert == "/etc/rhsm/ca/redhat-uep.pem"
        assert repos[0].sslclientkey == "/etc/pki/entitlement/123-key.pem"
        assert repos[0].sslclientcert == "/etc/pki/entitlement/123.pem"


@pytest.mark.parametrize("ssl_field,ssl_value", [
    pytest.param("sslcacert", "/some/ca.pem", id="sslcacert"),
    pytest.param("sslclientkey", "/some/key.pem", id="sslclientkey"),
    pytest.param("sslclientcert", "/some/cert.pem", id="sslclientcert"),
])
def test_rhsm_with_ssl_field_already_set_raises_error(tmp_path, ssl_field, ssl_value):
    """Test that InvalidRequestError is raised when rhsm=True and an ssl field is already set."""
    repo_kwargs = {
        "repo_id": "rhel",
        "baseurl": ["https://cdn.redhat.com/repo"],
        "rhsm": True,
        ssl_field: ssl_value,
    }
    repo = Repository.from_request(**repo_kwargs)
    config = SolverConfig(
        arch="x86_64",
        releasever="9",
        cachedir=str(tmp_path / "cache"),
        repos=[repo],
    )

    mock_subscriptions_instance = MagicMock()
    with patch("osbuild.solver.Subscriptions") as mock_subscriptions:
        mock_subscriptions.from_host_system.return_value = mock_subscriptions_instance
        with pytest.raises(
            InvalidRequestError,
            match=r"The sslcacert, sslclientkey, and sslclientcert fields cannot be set when rhsm: true is specified"
        ):
            DummySolver(config, persistdir=tmp_path / "persist")


@pytest.mark.parametrize("mock_setup,expected_msg_pattern", [
    pytest.param(
        lambda mock: setattr(
            mock, 'from_host_system',
            MagicMock(side_effect=RuntimeError("No RHSM secrets found"))
        ),
        r"The host system does not have any valid subscriptions. Subscribe it before specifying rhsm: true in "
        r"repositories \(error details: No RHSM secrets found; repo_id: rhel; "
        r"repo_urls: \['https://cdn.redhat.com/repo', 'https://cdn.redhat.com/repo2'\]\)",
        id="no-subscriptions",
    ),
    pytest.param(
        lambda mock: setattr(
            mock, 'from_host_system',
            MagicMock(return_value=MagicMock(
                get_secrets=MagicMock(side_effect=RuntimeError("No secrets for URL"))
            ))
        ),
        r"Error getting RHSM secrets for \['https://cdn\.redhat\.com/repo', 'https://cdn\.redhat\.com/repo2'\]: "
        r"No secrets for URL",
        id="no-secrets-for-urls",
    ),
])
def test_rhsm_errors_raise_no_rhsm_subscriptions_error(tmp_path, mock_setup, expected_msg_pattern):
    """Test that NoRHSMSubscriptionsError is raised when RHSM operations fail."""
    repo = Repository.from_request(
        repo_id="rhel",
        baseurl=[
            "https://cdn.redhat.com/repo",
            "https://cdn.redhat.com/repo2",
        ],
        rhsm=True,
    )
    config = SolverConfig(
        arch="x86_64",
        releasever="9",
        cachedir=str(tmp_path / "cache"),
        repos=[repo],
    )

    with patch("osbuild.solver.Subscriptions") as mock_subscriptions:
        mock_setup(mock_subscriptions)
        with pytest.raises(NoRHSMSubscriptionsError, match=expected_msg_pattern):
            DummySolver(config, persistdir=tmp_path / "persist")


def test_rhsm_subscription_lookup_cached_for_multiple_repos(tmp_path):
    """Test that Subscriptions.from_host_system is called only once for multiple rhsm repos."""
    repos = [
        Repository.from_request(repo_id="rhel-baseos", baseurl=["https://cdn.redhat.com/baseos"], rhsm=True),
        Repository.from_request(repo_id="rhel-appstream", baseurl=["https://cdn.redhat.com/appstream"], rhsm=True),
    ]
    config = SolverConfig(
        arch="x86_64",
        releasever="9",
        cachedir=str(tmp_path / "cache"),
        repos=repos,
    )

    mock_secrets = {
        "ssl_ca_cert": "/etc/rhsm/ca/redhat-uep.pem",
        "ssl_client_key": "/etc/pki/entitlement/123-key.pem",
        "ssl_client_cert": "/etc/pki/entitlement/123.pem",
    }
    mock_subscriptions_instance = MagicMock()
    mock_subscriptions_instance.get_secrets.return_value = mock_secrets

    with patch("osbuild.solver.Subscriptions") as mock_subscriptions:
        mock_subscriptions.from_host_system.return_value = mock_subscriptions_instance
        solver = DummySolver(config, persistdir=tmp_path / "persist")

        mock_subscriptions.from_host_system.assert_called_once()
        assert mock_subscriptions_instance.get_secrets.call_count == 2
        assert mock_subscriptions_instance.get_secrets.call_args_list == [
            call(["https://cdn.redhat.com/baseos"]),
            call(["https://cdn.redhat.com/appstream"]),
        ]
        assert solver.repo_ids_with_rhsm == {"rhel-baseos", "rhel-appstream"}


@pytest.mark.parametrize("rhsm_repo_ids,repo,expected_rhsm", [
    pytest.param(
        [],
        Repository(repo_id="fedora", baseurl=["http://example.com"]),
        False,
        id="empty-rhsm-list",
    ),
    pytest.param(
        ["rhel-baseos"],
        Repository(repo_id="fedora", baseurl=["http://example.com"]),
        False,
        id="repo-not-in-rhsm-list",
    ),
    pytest.param(
        ["rhel-baseos"],
        Repository(repo_id="rhel-baseos", baseurl=["http://example.com"]),
        True,
        id="repo-in-rhsm-list",
    ),
    pytest.param(
        ["rhel-baseos", "rhel-appstream"],
        Repository(repo_id="rhel-appstream", baseurl=["http://example.com"]),
        True,
        id="repo-in-multi-item-rhsm-list",
    ),
])
def test_mark_repo_if_rhsm(tmp_path, rhsm_repo_ids, repo, expected_rhsm):
    """Test that set_rhsm_flag correctly sets the rhsm flag based on repo_ids_with_rhsm."""
    config = SolverConfig(
        arch="x86_64",
        releasever="9",
        cachedir=str(tmp_path / "cache"),
        repos=[],
        root_dir="/",
    )

    with patch("osbuild.solver.Subscriptions"):
        solver = DummySolver(config, persistdir=tmp_path / "persist")
        solver.repo_ids_with_rhsm = rhsm_repo_ids

        solver.set_rhsm_flag(repo)

        assert repo.rhsm == expected_rhsm
