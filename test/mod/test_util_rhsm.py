#
# Tests for the `osbuild.util.rhsm` module.
#

from io import StringIO

from osbuild.util.rhsm import Subscriptions

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


def test_from_host_system():
    #
    # Test the `ioctl_get_immutable()` helper and make sure it works
    # as intended.
    #
    subscriptions = Subscriptions.parse_repo_file(StringIO(REPO_FILE))
    rpm_url_cases = [
        {
            "url": "https://cdn.redhat.com/8/jws/1.0/risc_v/os/Packages/fishy-fish-1-1.el8.risc_v.rpm",
            "success": True,
            "key": "2",
        },
        {
            "url": "https://cdn.redhat.com/8/jws/1.0/os/Packages/fishy-fish-1-1.el8.risc_v.rpm",
            "success": False,
            "key": "",
        },
        {"url": "https://cdn.redhat.com/1.0/x86_64/os/Packages/aaa.rpm", "success": True, "key": "1"},
    ]
    for test_case in rpm_url_cases:
        try:
            secrets = subscriptions.get_secrets(test_case["url"])
        except RuntimeError as e:
            if not test_case["success"]:
                continue

            raise e

        assert test_case["success"]  # Verify this test case should pass
        assert secrets["ssl_ca_cert"] == "/etc/rhsm/ca/redhat-uep.pem"
        assert secrets["ssl_client_key"] == f'/etc/pki/entitlement/{test_case["key"]}-key.pem'
        assert secrets["ssl_client_cert"] == f'/etc/pki/entitlement/{test_case["key"]}.pem'
