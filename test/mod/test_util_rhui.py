import base64
from unittest.mock import MagicMock, patch

import pytest

from osbuild.util import rhui


class TestCloudDetection:
    """Test detect_cloud_provider() probing logic."""

    @patch("urllib.request.urlopen")
    def test_detect_aws(self, mock_urlopen):
        """AWS is detected when IMDSv2 token endpoint responds."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"fake-token"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        assert rhui.detect_cloud_provider() == "aws"

    @patch("urllib.request.urlopen")
    def test_detect_gcp(self, mock_urlopen):
        """GCP is detected when AWS fails but GCP metadata responds."""
        call_count = 0

        def side_effect(_req, **_kwargs):
            nonlocal call_count
            call_count += 1
            # First call is AWS token (PUT) — fail it
            if call_count == 1:
                raise OSError("connection refused")
            # Second call is GCP metadata — succeed
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"ok"
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        mock_urlopen.side_effect = side_effect
        assert rhui.detect_cloud_provider() == "gcp"

    @patch("urllib.request.urlopen")
    def test_detect_azure(self, mock_urlopen):
        """Azure is detected when AWS and GCP fail but Azure IMDS responds."""
        call_count = 0

        def side_effect(_req, **_kwargs):
            nonlocal call_count
            call_count += 1
            # 1=AWS token, 2=GCP metadata — fail both
            if call_count <= 2:
                raise OSError("connection refused")
            # 3=Azure IMDS — succeed
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"compute": {}}'
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        mock_urlopen.side_effect = side_effect
        assert rhui.detect_cloud_provider() == "azure"

    @patch("urllib.request.urlopen")
    def test_detect_none(self, mock_urlopen):
        """Returns None when no cloud IMDS is reachable."""
        mock_urlopen.side_effect = OSError("connection refused")
        assert rhui.detect_cloud_provider() is None


class TestAWSHeaders:
    """Test AWS IMDS interaction and header generation."""

    @patch("osbuild.util.rhui._aws_imds_get")
    @patch("osbuild.util.rhui._aws_get_token")
    def test_aws_get_identity_headers(self, mock_token, mock_imds_get):
        mock_token.return_value = "fake-token"

        doc_bytes = b'{"instanceId": "i-1234"}'
        # IMDS returns base64-encoded signature text
        sig_from_imds = b"c2lnbmF0dXJlLWJ5dGVz"

        mock_imds_get.side_effect = [doc_bytes, sig_from_imds]

        headers = rhui._aws_get_identity_headers()  # pylint: disable=protected-access

        assert len(headers) == 2
        assert headers[0].startswith("X-RHUI-ID: ")
        assert headers[1].startswith("X-RHUI-SIGNATURE: ")

        # Verify the doc is urlsafe-base64-encoded
        decoded_doc = base64.urlsafe_b64decode(headers[0].split(": ", 1)[1])
        assert decoded_doc == doc_bytes

        # The signature from IMDS is passed through urlsafe_b64encode
        # directly (matching the amazon-id DNF plugin behavior)
        decoded_sig = base64.urlsafe_b64decode(headers[1].split(": ", 1)[1])
        assert decoded_sig == sig_from_imds


class TestGCPHeaders:
    """Test GCP metadata interaction and header generation."""

    @patch("osbuild.util.rhui._gcp_metadata_get")
    def test_gcp_get_identity_headers(self, mock_metadata_get):
        doc_bytes = b"gcp-identity-token"
        sig_bytes = b'{"access_token": "ya29.xxx"}'

        mock_metadata_get.side_effect = [doc_bytes, sig_bytes]

        headers = rhui._gcp_get_identity_headers()  # pylint: disable=protected-access

        assert len(headers) == 2
        assert headers[0].startswith("X-RHUI-ID: ")
        assert headers[1].startswith("X-RHUI-SIGNATURE: ")

        decoded_doc = base64.b64decode(headers[0].split(": ", 1)[1])
        assert decoded_doc == doc_bytes

        decoded_sig = base64.b64decode(headers[1].split(": ", 1)[1])
        assert decoded_sig == sig_bytes


class TestAzureNoHeaders:
    """Azure RHUI uses cert-only auth, no extra headers needed."""

    @patch("osbuild.util.rhui.Subscriptions")
    @patch("osbuild.util.rhui.detect_cloud_provider")
    def test_azure_returns_empty_headers(self, mock_detect, mock_subs_cls):
        mock_detect.return_value = "azure"

        mock_subs = MagicMock()
        mock_subs.get_secrets.return_value = {
            "ssl_ca_cert": "/etc/pki/rhui/ca.crt",
            "ssl_client_key": "/etc/pki/rhui/key.pem",
            "ssl_client_cert": "/etc/pki/rhui/cert.pem",
        }
        mock_subs_cls._from_rhui_repo_files.return_value = mock_subs

        result = rhui.get_rhui_secrets(["https://rhui.azure.example.com/repo"])

        assert not result["headers"]
        assert result["ssl_ca_cert"] == "/etc/pki/rhui/ca.crt"
        assert result["ssl_client_key"] == "/etc/pki/rhui/key.pem"
        assert result["ssl_client_cert"] == "/etc/pki/rhui/cert.pem"


class TestGetRhuiSecrets:
    """Integration tests for the main get_rhui_secrets() entry point."""

    @patch("osbuild.util.rhui._aws_get_identity_headers")
    @patch("osbuild.util.rhui.Subscriptions")
    @patch("osbuild.util.rhui.detect_cloud_provider")
    def test_aws_combined(self, mock_detect, mock_subs_cls, mock_aws_headers):
        mock_detect.return_value = "aws"
        mock_aws_headers.return_value = [
            "X-RHUI-ID: abc123",
            "X-RHUI-SIGNATURE: sig456",
        ]

        mock_subs = MagicMock()
        mock_subs.get_secrets.return_value = {
            "ssl_ca_cert": "/etc/pki/rhui/ca.crt",
            "ssl_client_key": "",
            "ssl_client_cert": "",
        }
        mock_subs_cls._from_rhui_repo_files.return_value = mock_subs

        result = rhui.get_rhui_secrets(["https://rhui.aws.example.com/repo"])

        assert result["ssl_ca_cert"] == "/etc/pki/rhui/ca.crt"
        assert result["ssl_client_key"] == ""
        assert result["ssl_client_cert"] == ""
        assert len(result["headers"]) == 2
        assert "X-RHUI-ID: abc123" in result["headers"]
        assert "X-RHUI-SIGNATURE: sig456" in result["headers"]

    @patch("osbuild.util.rhui._gcp_get_identity_headers")
    @patch("osbuild.util.rhui.Subscriptions")
    @patch("osbuild.util.rhui.detect_cloud_provider")
    def test_gcp_combined(self, mock_detect, mock_subs_cls, mock_gcp_headers):
        mock_detect.return_value = "gcp"
        mock_gcp_headers.return_value = [
            "X-RHUI-ID: gcp-id",
            "X-RHUI-SIGNATURE: gcp-sig",
        ]

        mock_subs = MagicMock()
        mock_subs.get_secrets.return_value = {
            "ssl_ca_cert": "/etc/pki/rhui/gcp-ca.crt",
            "ssl_client_key": "",
            "ssl_client_cert": "",
        }
        mock_subs_cls._from_rhui_repo_files.return_value = mock_subs

        result = rhui.get_rhui_secrets(["https://rhui.gcp.example.com/repo"])

        assert result["ssl_ca_cert"] == "/etc/pki/rhui/gcp-ca.crt"
        assert len(result["headers"]) == 2

    @patch("osbuild.util.rhui.Subscriptions")
    @patch("osbuild.util.rhui.detect_cloud_provider")
    def test_fallback_when_no_url_match(self, mock_detect, mock_subs_cls):
        """When get_secrets() raises RuntimeError, fall back to first RHUI repo's certs."""
        mock_detect.return_value = "azure"

        mock_subs = MagicMock()
        mock_subs.get_secrets.side_effect = RuntimeError("no match")
        mock_subs.repositories = {
            "rhel-8-baseos-rhui-rpms": {
                "sslcacert": "/fallback/ca.crt",
                "sslclientkey": "/fallback/key.pem",
                "sslclientcert": "/fallback/cert.pem",
            }
        }
        mock_subs_cls._from_rhui_repo_files.return_value = mock_subs

        result = rhui.get_rhui_secrets(["https://unknown.example.com/repo"])

        assert result["ssl_ca_cert"] == "/fallback/ca.crt"
        assert result["ssl_client_key"] == "/fallback/key.pem"
        assert not result["headers"]


class TestIMDSFailure:
    """get_rhui_secrets() raises when not on any cloud."""

    @patch("osbuild.util.rhui.detect_cloud_provider")
    def test_raises_when_no_cloud(self, mock_detect):
        mock_detect.return_value = None
        with pytest.raises(RuntimeError, match="Cannot detect cloud provider"):
            rhui.get_rhui_secrets(["https://example.com/repo"])
