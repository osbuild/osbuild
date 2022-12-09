"""Red Hat Subscription Manager support module

This module implements utilities that help with interactions
with the subscriptions attached to the host machine.
"""

import configparser
import contextlib
import glob
import os
import re


class Subscriptions:
    def __init__(self, repositories):
        self.repositories = repositories
        # These are used as a fallback if the repositories don't
        # contain secrets for a requested URL.
        self.secrets = None

    def get_fallback_rhsm_secrets(self):
        rhsm_secrets = {
            'ssl_ca_cert': "/etc/rhsm/ca/redhat-uep.pem",
            'ssl_client_key': "",
            'ssl_client_cert': ""
        }

        keys = glob.glob("/etc/pki/entitlement/*-key.pem")
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
        """Returns the consumer identity certificate which uniquely identifies the system"""
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
        """Read redhat.repo file and process the list of repositories in there."""
        ret = cls(None)
        with contextlib.suppress(FileNotFoundError):
            with open("/etc/yum.repos.d/redhat.repo", "r", encoding="utf8") as fp:
                ret = cls.parse_repo_file(fp)

        with contextlib.suppress(RuntimeError):
            ret.get_fallback_rhsm_secrets()

        if not ret.repositories and not ret.secrets:
            raise RuntimeError("No RHSM secrets found on this host.")

        return ret

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

        return re.compile(input_url)

    @classmethod
    def parse_repo_file(cls, fp):
        """Take a file object and reads its content assuming it is a .repo file."""
        parser = configparser.ConfigParser()
        parser.read_file(fp)

        repositories = {}
        for section in parser.sections():
            current = {
                "matchurl": cls._process_baseurl(parser.get(section, "baseurl"))
            }
            for parameter in ["sslcacert", "sslclientkey", "sslclientcert"]:
                current[parameter] = parser.get(section, parameter)

            repositories[section] = current

        return cls(repositories)

    def get_secrets(self, url):
        # Try to find a matching URL from redhat.repo file first
        if self.repositories is not None:
            for parameters in self.repositories.values():
                if parameters["matchurl"].match(url) is not None:
                    return {
                        "ssl_ca_cert": parameters["sslcacert"],
                        "ssl_client_key": parameters["sslclientkey"],
                        "ssl_client_cert": parameters["sslclientcert"]
                    }

        # In case there is no matching URL, try the fallback
        if self.secrets:
            return self.secrets

        raise RuntimeError(f"There are no RHSM secret associated with {url}")
