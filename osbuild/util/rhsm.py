"""Red Hat Subscription Manager support module

This module implements utilities that help with interactions
with the subscriptions attached to the host machine.
"""

import configparser
import re


class Subscriptions:
    def __init__(self, repositories):
        self.repositories = repositories

    @classmethod
    def from_host_system(cls):
        """Read redhat.repo file and process the list of repositories in there."""
        with open("/etc/yum.repos.d/redhat.repo", "r") as fp:
            return cls.parse_repo_file(fp)

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

        repositories = dict()
        for section in parser.sections():
            current = {
                "matchurl": cls._process_baseurl(parser.get(section, "baseurl"))
            }
            for parameter in ["sslcacert", "sslclientkey", "sslclientcert"]:
                current[parameter] = parser.get(section, parameter)

            repositories[section] = current

        return cls(repositories)

    def get_secrets(self, url):
        for parameters in self.repositories.values():
            if parameters["matchurl"].match(url) is not None:
                return {
                    "ssl_ca_cert": parameters["sslcacert"],
                    "ssl_client_key": parameters["sslclientkey"],
                    "ssl_client_cert": parameters["sslclientcert"]
                }

        raise RuntimeError(f"There are no RHSM secret associated with {url}")
