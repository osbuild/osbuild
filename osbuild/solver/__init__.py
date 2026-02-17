import abc
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from osbuild.solver.exceptions import GPGKeyReadError, InvalidRequestError, NoRHSMSubscriptionsError
from osbuild.solver.model import DepsolveResult, DumpResult, Repository, SearchResult
from osbuild.solver.request import DepsolveCmdArgs, SearchCmdArgs, SolverConfig
from osbuild.util.rhsm import Subscriptions


class Solver(abc.ABC):
    @abc.abstractmethod
    def dump(self) -> DumpResult:
        pass

    @abc.abstractmethod
    def depsolve(self, args: DepsolveCmdArgs) -> DepsolveResult:
        pass

    @abc.abstractmethod
    def search(self, args: SearchCmdArgs) -> SearchResult:
        pass


class SolverBase(Solver):
    # put any shared helpers in here

    # Override this in the subclass
    SOLVER_NAME = "unknown"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.SOLVER_NAME == SolverBase.SOLVER_NAME:
            raise ValueError(f"{cls.__name__} must override SOLVER_NAME")

    def __init__(
        self,
        config: SolverConfig,
        persistdir: os.PathLike,
        license_index_path: Optional[os.PathLike] = None,
    ):
        self.config = config
        self.persistdir = persistdir
        self.license_index_path = license_index_path
        # Set of repository IDs that need RHSM secrets
        self.repo_ids_with_rhsm = set()

        # Resolve RHUI secrets first (they use cloud certs, not RHSM)
        self._resolve_rhui_secrets()

        # Get the RHSM secrets for the repositories that need them
        subscriptions = None
        for repo in self.config.repos or []:
            if not repo.rhsm or repo.rhui:
                continue

            repo_urls = []
            if repo.baseurl:
                repo_urls.extend(repo.baseurl)
            if repo.metalink:
                repo_urls.append(repo.metalink)
            if repo.mirrorlist:
                repo_urls.append(repo.mirrorlist)

            if subscriptions is None:
                try:
                    subscriptions = Subscriptions.from_host_system()
                except RuntimeError as e:
                    raise NoRHSMSubscriptionsError("The host system does not have any valid subscriptions. "
                                                   "Subscribe it before specifying rhsm: true in repositories "
                                                   f"(error details: {e}; repo_id: {repo.repo_id}; "
                                                   f"repo_urls: {repo_urls})") from e

            # We will override the sslcacert, sslclientkey, and sslclientcert with the ones from the subscriptions
            # Return an error if the fields are already set
            if repo.sslcacert or repo.sslclientkey or repo.sslclientcert:
                raise InvalidRequestError("The sslcacert, sslclientkey, and sslclientcert fields cannot be set "
                                          "when rhsm: true is specified")

            try:
                secrets = subscriptions.get_secrets(repo_urls)
                repo.sslcacert = secrets["ssl_ca_cert"]
                repo.sslclientkey = secrets["ssl_client_key"]
                repo.sslclientcert = secrets["ssl_client_cert"]
            except RuntimeError as e:
                raise NoRHSMSubscriptionsError(f"Error getting RHSM secrets for {repo_urls}: {e}") from e

            self.repo_ids_with_rhsm.add(repo.repo_id)

    def _resolve_rhui_secrets(self):
        """Resolve SSL secrets and identity headers for RHUI repositories.

        RHUI (Red Hat Update Infrastructure) repos use cloud-specific SSL
        certificates from /etc/pki/rhui/ rather than RHSM entitlement certs.
        AWS and GCP also require X-RHUI-ID/X-RHUI-SIGNATURE identity headers.
        """
        rhui_repos = [r for r in (self.config.repos or []) if r.rhui]
        if not rhui_repos:
            self.rhui_headers = []
            return

        # Discover RHUI secrets from host repo files
        rhui_subscriptions = Subscriptions._from_rhui_repo_files()
        if not rhui_subscriptions.repositories:
            raise NoRHSMSubscriptionsError(
                "No RHUI repository files found on this host. "
                "Ensure the RHUI client package is installed."
            )

        # Fetch cloud identity headers (AWS/GCP need them, Azure does not)
        try:
            from osbuild.util.rhui import (
                _aws_get_identity_headers,
                _gcp_get_identity_headers,
                detect_cloud_provider,
            )
            provider = detect_cloud_provider()
            if provider == "aws":
                self.rhui_headers = _aws_get_identity_headers()
            elif provider == "gcp":
                self.rhui_headers = _gcp_get_identity_headers()
            else:
                self.rhui_headers = []
        except Exception:
            self.rhui_headers = []

        for repo in rhui_repos:
            repo_urls = []
            if repo.baseurl:
                repo_urls.extend(repo.baseurl)
            if repo.metalink:
                repo_urls.append(repo.metalink)
            if repo.mirrorlist:
                repo_urls.append(repo.mirrorlist)

            # Match repo URL to RHUI repo file entries for correct certs
            try:
                secrets = rhui_subscriptions.get_secrets(repo_urls)
            except RuntimeError:
                # Fall back to first available if URL matching fails
                first = next(iter(rhui_subscriptions.repositories.values()))
                secrets = {
                    "ssl_ca_cert": first["sslcacert"],
                    "ssl_client_key": first["sslclientkey"],
                    "ssl_client_cert": first["sslclientcert"],
                }

            repo.sslcacert = secrets["ssl_ca_cert"]
            repo.sslclientkey = secrets["ssl_client_key"]
            repo.sslclientcert = secrets["ssl_client_cert"]
            # Mark as RHSM so the response correctly flags these repos
            self.repo_ids_with_rhsm.add(repo.repo_id)

    def set_rhsm_flag(self, repo: Repository) -> None:
        """
        Set the rhsm flag on the repository based on repo_ids_with_rhsm.
        Sets the flag to True if repo.repo_id is in the set of RHSM repos, False otherwise.
        Otherwise, set it to False.
        """
        repo.rhsm = repo.repo_id in self.repo_ids_with_rhsm


def modify_rootdir_path(path, root_dir):
    if path and root_dir:
        # if the root_dir is set, we need to translate the key path to be under this directory
        return os.path.join(root_dir, path.lstrip("/"))
    return path


def read_keys(paths, root_dir=None):
    keys = []
    for path in paths:
        url = urllib.parse.urlparse(path)
        if url.scheme == "file":
            path = url.path
            path = modify_rootdir_path(path, root_dir)
            try:
                with open(path, mode="r", encoding="utf-8") as keyfile:
                    keys.append(keyfile.read())
            except Exception as e:
                raise GPGKeyReadError(f"error loading gpg key from {path}: {e}") from e
        elif url.scheme in ["http", "https"]:
            try:
                resp = urllib.request.urlopen(urllib.request.Request(path))
                keys.append(resp.read().decode())
            except urllib.error.URLError as e:
                raise GPGKeyReadError(f"error reading remote gpg key at {path}: {e}") from e
        else:
            raise GPGKeyReadError(f"unknown url scheme for gpg key: {url.scheme} ({path})")
    return keys
