"""Red Hat Subscription Manager and RHUI support module

This module implements utilities that help with interactions
with the subscriptions attached to the host machine, either
via RHSM (Red Hat Subscription Manager) or RHUI (Red Hat
Update Infrastructure).
"""

import configparser
import contextlib
import glob
import os
import re
from typing import List

# Common RHUI repo file patterns across cloud providers
RHUI_REPO_GLOB_PATTERN = "/etc/yum.repos.d/*rhui*.repo"


class Subscriptions:
    DEFAULT_SSL_CA_CERT = "/etc/rhsm/ca/redhat-uep.pem"
    DEFAULT_ENTITLEMENT_DIR = "/etc/pki/entitlement"
    DEFAULT_REPO_FILE = "/etc/yum.repos.d/redhat.repo"

    def __init__(self, repositories):
        self.repositories = repositories
        # These are used as a fallback if the repositories don't
        # contain secrets for a requested URL.
        self.secrets = None

        if self.is_container_with_rhsm_secrets():
            self.DEFAULT_SSL_CA_CERT = "/run/secrets/rhsm/ca/redhat-uep.pem"
            self.DEFAULT_ENTITLEMENT_DIR = "/run/secrets/etc-pki-entitlement"
            self.DEFAULT_REPO_FILE = "/run/secrets/redhat.repo"

    @staticmethod
    def is_container_with_rhsm_secrets():
        """Detect if we are running inside a podman container and RHSM secrets are available."""
        return os.path.exists("/run/.containerenv") and os.path.exists("/run/secrets")

    def get_fallback_rhsm_secrets(self):
        rhsm_secrets = {
            'ssl_ca_cert': self.DEFAULT_SSL_CA_CERT,
            'ssl_client_key': "",
            'ssl_client_cert': ""
        }

        keys = glob.glob(f"{self.DEFAULT_ENTITLEMENT_DIR}/*-key.pem")
        for key in keys:
            # The key and cert have the same prefix
            cert = key.rstrip("-key.pem") + ".pem"
            # The key is only valid if it has a matching cert
            if os.path.exists(cert):
                rhsm_secrets['ssl_client_key'] = key
                rhsm_secrets['ssl_client_cert'] = cert
                # Once the dictionary is complete, assign it to the object
                self.secrets = rhsm_secrets

        raise RuntimeError("no matching rhsm key and cert")

    @staticmethod
    def get_consumer_secrets():
        """Returns the consumer identity certificate which uniquely identifies the system.

        Will fail when running in a container. Used by ostree.
        """
        key = "/etc/pki/consumer/key.pem"
        cert = "/etc/pki/consumer/cert.pem"

        if not (os.path.exists(key) and os.path.exists(cert)):
            raise RuntimeError("rhsm consumer key and cert not found")

        return {
            'consumer_key': key,
            'consumer_cert': cert
        }

    @classmethod
    def from_host_system(cls):
        """Read host repo files and extract subscription secrets.

        Checks for credentials in the following order:
        1. RHSM: /etc/yum.repos.d/redhat.repo (subscription-manager managed)
        2. RHUI: /etc/yum.repos.d/rhui-*.repo (RHUI client managed)
        3. Fallback: entitlement certificates in /etc/pki/entitlement/
        """
        ret = cls(None)
        with contextlib.suppress(FileNotFoundError):
            with open(cls.DEFAULT_REPO_FILE, "r", encoding="utf8") as fp:
                ret = cls.parse_repo_file(fp)

        # If no RHSM repos found, try RHUI repo files
        if not ret.repositories:
            ret = cls._from_rhui_repo_files()

        with contextlib.suppress(RuntimeError):
            ret.get_fallback_rhsm_secrets()

        if not ret.repositories and not ret.secrets:
            raise RuntimeError("No RHSM or RHUI secrets found on this host.")

        return ret

    @classmethod
    def _from_rhui_repo_files(cls):
        """Read RHUI repo files and extract repository configurations.

        RHUI client packages (e.g. rhui-azure-rhel9, rhui-amazon-rhel9)
        install repo files matching /etc/yum.repos.d/rhui-*.repo that
        point to cloud-local RHUI mirrors with their own CA and optional
        client certificates.
        """
        merged = cls(None)
        rhui_files = sorted(glob.glob(RHUI_REPO_GLOB_PATTERN))
        for repo_file in rhui_files:
            with contextlib.suppress(FileNotFoundError):
                with open(repo_file, "r", encoding="utf8") as fp:
                    parsed = cls.parse_repo_file(fp)
                    if parsed.repositories:
                        if merged.repositories is None:
                            merged.repositories = {}
                        merged.repositories.update(parsed.repositories)
        return merged

    @staticmethod
    def _process_baseurl(input_url):
        """Create a regex from a baseurl.

        The osbuild manifest format does not contain information about repositories.
        It only includes URLs of each RPM. In order to make this RHSM support work,
        osbuild needs to find a relation between a "baseurl" in a *.repo file and the
        URL given in the manifest. To do so, it creates a regex from all baseurls
        found in the *.repo file and matches them against the URL.
        """
        # First escape meta characters that might occur in a URL
        input_url = re.escape(input_url)

        # Now replace variables with regexes (see man 5 yum.conf for the list)
        for variable in ["\\$releasever", "\\$arch", "\\$basearch", "\\$uuid"]:
            input_url = input_url.replace(variable, "[^/]*")

        # Handle cloud-specific placeholders (e.g. AWS RHUI uses literal
        # REGION in mirrorlist URLs, replaced at runtime by the DNF plugin)
        input_url = input_url.replace("REGION", "[^./]*")

        # Pulp-based CDN (RHUI) uses /pulp/mirror/ for mirrorlist/repodata
        # requests but /pulp/content/ for actual content downloads.  Make
        # the regex match either variant so that repo-file URLs can be
        # matched against manifest download URLs.
        # Handle both escaped (Python 3.6: \/) and unescaped (Python 3.7+: /) slashes
        input_url = input_url.replace(r"pulp\/mirror", r"pulp\/(?:mirror|content)")
        input_url = input_url.replace("pulp/mirror", "pulp/(?:mirror|content)")

        return re.compile(input_url)

    @classmethod
    def parse_repo_file(cls, fp):
        """Take a file object and reads its content assuming it is a .repo file.

        Handles both RHSM (redhat.repo) and RHUI repo files. RHUI repos
        may not have sslclientkey/sslclientcert if the cloud instance
        identity is used for authentication instead.
        """
        parser = configparser.ConfigParser()
        parser.read_file(fp)

        repositories = {}
        for section in parser.sections():
            baseurl = parser.get(section, "baseurl", fallback=None)
            mirrorlist = parser.get(section, "mirrorlist", fallback=None)
            url = baseurl or mirrorlist
            if not url:
                continue

            current = {
                "matchurl": cls._process_baseurl(url)
            }

            # On RHEL systems registered to Insights, the redhat.repo exists and contains entitlement
            # certificates, however, "sslcacert" is unset and rhsm dnf plugin automatically sets that
            # to /etc/rhsm/ca/redhat-uep.pem or /run/secrets/rhsm/ca/redhat-uep.pem respectively.
            current["sslcacert"] = parser.get(section, "sslcacert", fallback=cls.DEFAULT_SSL_CA_CERT)

            # Client certificates: always present in RHSM redhat.repo, but
            # may be absent in RHUI repo files (cloud RHUI uses instance
            # identity for auth instead of client certificates).
            current["sslclientkey"] = parser.get(section, "sslclientkey", fallback="")
            current["sslclientcert"] = parser.get(section, "sslclientcert", fallback="")

            repositories[section] = current

        return cls(repositories)

    def get_secrets(self, urls: List[str]):
        """
        Get the RHSM secrets for a list of URLs.

        The URLs can be a baseurl, metalink, or mirrorlist. The list can
        even combine all types of URLs. The function will iterate over the list
        and try to find a matching URL in the redhat.repo file. The function
        returns secrets for the first matching URL.

        If no matching URL is found, the function will try the fallback
        secrets. If no fallback secrets are found, the function will raise
        a RuntimeError.
        """
        # Try to find a matching URL from redhat.repo file first
        if self.repositories is not None:
            for parameters in self.repositories.values():
                for url in urls:
                    if parameters["matchurl"].match(url) is not None:
                        return {
                            "ssl_ca_cert": parameters["sslcacert"],
                            "ssl_client_key": parameters["sslclientkey"],
                            "ssl_client_cert": parameters["sslclientcert"]
                        }

        # In case there is no matching URL, try the fallback
        if self.secrets:
            return self.secrets

        raise RuntimeError(f"There are no RHSM secret associated with {urls}")
