"""Cloud RHUI (Red Hat Update Infrastructure) identity support.

This module detects the cloud provider (AWS, Azure, GCP) by probing
instance metadata endpoints, fetches the identity headers required by
RHUI content servers, and combines them with SSL certificates discovered
from host RHUI repo files.

AWS and GCP RHUI mirrors require X-RHUI-ID and X-RHUI-SIGNATURE HTTP
headers on every request.  Azure RHUI uses certificate + IP-range
authentication only, so no extra headers are needed.
"""

import base64
import contextlib
import urllib.request
from typing import List, Optional

from osbuild.util.rhsm import Subscriptions

# Timeout for IMDS probes (seconds)
_IMDS_TIMEOUT = 5

# --- AWS IMDSv2 ---------------------------------------------------------

_AWS_TOKEN_URL = "http://169.254.169.254/latest/api/token"
_AWS_IDENTITY_DOC_URL = "http://169.254.169.254/latest/dynamic/instance-identity/document"
_AWS_IDENTITY_SIG_URL = "http://169.254.169.254/latest/dynamic/instance-identity/signature"


def _aws_get_token() -> str:
    """Obtain an IMDSv2 session token."""
    req = urllib.request.Request(
        _AWS_TOKEN_URL,
        method="PUT",
        headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
    )
    with urllib.request.urlopen(req, timeout=_IMDS_TIMEOUT) as resp:
        return resp.read().decode("utf-8")


def _aws_imds_get(url: str, token: str) -> bytes:
    """GET from AWS IMDS using a session token."""
    req = urllib.request.Request(
        url,
        headers={"X-aws-ec2-metadata-token": token},
    )
    with urllib.request.urlopen(req, timeout=_IMDS_TIMEOUT) as resp:
        return resp.read()


def _aws_get_identity_headers() -> List[str]:
    """Fetch AWS instance identity document + signature and return RHUI headers."""
    token = _aws_get_token()
    doc = _aws_imds_get(_AWS_IDENTITY_DOC_URL, token)
    sig = _aws_imds_get(_AWS_IDENTITY_SIG_URL, token)

    doc_b64 = base64.b64encode(doc).decode("utf-8")
    # The signature from IMDS is already base64-encoded text, but RHUI
    # expects the raw signature bytes re-encoded, so we decode then
    # re-encode to get a single clean base64 line without whitespace.
    sig_b64 = base64.b64encode(base64.b64decode(sig)).decode("utf-8")

    return [
        f"X-RHUI-ID: {doc_b64}",
        f"X-RHUI-SIGNATURE: {sig_b64}",
    ]


# --- GCP ----------------------------------------------------------------

_GCP_IDENTITY_DOC_URL = (
    "http://metadata.google.internal/computeMetadata/v1/"
    "instance/service-accounts/default/identity"
    "?audience=rhui&format=full"
)
_GCP_IDENTITY_SIG_URL = (
    "http://metadata.google.internal/computeMetadata/v1/"
    "instance/service-accounts/default/token"
)


def _gcp_metadata_get(url: str) -> bytes:
    """GET from GCP metadata server."""
    req = urllib.request.Request(
        url,
        headers={"Metadata-Flavor": "Google"},
    )
    with urllib.request.urlopen(req, timeout=_IMDS_TIMEOUT) as resp:
        return resp.read()


def _gcp_get_identity_headers() -> List[str]:
    """Fetch GCP instance identity and return RHUI headers."""
    doc = _gcp_metadata_get(_GCP_IDENTITY_DOC_URL)
    sig = _gcp_metadata_get(_GCP_IDENTITY_SIG_URL)

    doc_b64 = base64.b64encode(doc).decode("utf-8")
    sig_b64 = base64.b64encode(sig).decode("utf-8")

    return [
        f"X-RHUI-ID: {doc_b64}",
        f"X-RHUI-SIGNATURE: {sig_b64}",
    ]


# --- Azure (no extra headers) ------------------------------------------

_AZURE_IMDS_URL = (
    "http://169.254.169.254/metadata/instance"
    "?api-version=2021-02-01"
)


# --- Cloud detection ----------------------------------------------------

def detect_cloud_provider() -> Optional[str]:
    """Detect the cloud provider by probing IMDS endpoints.

    Returns "aws", "gcp", "azure", or None.
    """
    # AWS: try IMDSv2 token endpoint
    with contextlib.suppress(Exception):
        _aws_get_token()
        return "aws"

    # GCP: metadata server
    with contextlib.suppress(Exception):
        _gcp_metadata_get(
            "http://metadata.google.internal/computeMetadata/v1/"
        )
        return "gcp"

    # Azure: IMDS with Metadata header
    with contextlib.suppress(Exception):
        req = urllib.request.Request(
            _AZURE_IMDS_URL,
            headers={"Metadata": "true"},
        )
        urllib.request.urlopen(req, timeout=_IMDS_TIMEOUT)
        return "azure"

    return None


# --- Main entry point ---------------------------------------------------

def get_rhui_secrets(urls: List[str]) -> dict:
    """Get RHUI secrets (SSL certs + cloud identity headers) for downloading.

    Detects the cloud provider, fetches identity headers when required
    (AWS, GCP), and discovers SSL certificates from host RHUI repo files
    via the existing Subscriptions class.

    Returns a dict with keys: ssl_ca_cert, ssl_client_key,
    ssl_client_cert, headers.
    """
    provider = detect_cloud_provider()
    if provider is None:
        raise RuntimeError(
            "Cannot detect cloud provider; "
            "RHUI secrets are only available on cloud instances"
        )

    # Fetch cloud identity headers (AWS/GCP) or empty list (Azure)
    if provider == "aws":
        headers = _aws_get_identity_headers()
    elif provider == "gcp":
        headers = _gcp_get_identity_headers()
    else:
        headers = []

    # Get SSL certs from host RHUI repo files (not RHSM redhat.repo)
    subscriptions = Subscriptions._from_rhui_repo_files()
    try:
        certs = subscriptions.get_secrets(urls)
    except RuntimeError:
        # No matching URL — fall back to first available RHUI repo's certs
        if subscriptions.repositories:
            first = next(iter(subscriptions.repositories.values()))
            certs = {
                "ssl_ca_cert": first.get("sslcacert", ""),
                "ssl_client_key": first.get("sslclientkey", ""),
                "ssl_client_cert": first.get("sslclientcert", ""),
            }
        else:
            certs = {
                "ssl_ca_cert": "",
                "ssl_client_key": "",
                "ssl_client_cert": "",
            }

    return {
        "ssl_ca_cert": certs.get("ssl_ca_cert", ""),
        "ssl_client_key": certs.get("ssl_client_key", ""),
        "ssl_client_cert": certs.get("ssl_client_cert", ""),
        "headers": headers,
    }
