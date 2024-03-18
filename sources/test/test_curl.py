#!/usr/bin/python3

import pathlib
import subprocess
import textwrap
from unittest.mock import patch

import pytest

from osbuild import testutil
from osbuild.util.checksum import verify_file

SOURCES_NAME = "org.osbuild.curl"

TEST_SOURCE_PAIRS = [
    {
        # sha256("0")
        "checksum": "sha256:5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9",
        "url": "http://example.com/file/0",
    }, {
        # sha256("1")
        "checksum": "sha256:6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
        "url": "http://example.com/file/1",
        "insecure": True,
    }, {
        # sha256("2")
        "checksum": "sha256:d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
        "url": "http://example.com/file/2",
        "secrets": {
            "ssl_ca_cert": "some-ssl_ca_cert",
        },
    }, {
        # sha256("3")
        "checksum": "sha256:4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
        "url": "http://example.com/file/3",
        "secrets": {
            "ssl_client_cert": "some-ssl_client_cert",
            "ssl_client_key": "some-ssl_client_key",
        },
    },
]


def test_curl_gen_download_config(tmp_path, sources_module):
    config_path = tmp_path / "curl-config.txt"
    # pylint: disable=W0212
    sources_module._gen_curl_download_config(TEST_SOURCE_PAIRS, config_path)
    assert config_path.exists()
    assert config_path.read_text(encoding="utf8") == textwrap.dedent("""\
    url = "http://example.com/file/0"
    output = "sha256:5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9"
    no-insecure

    url = "http://example.com/file/1"
    output = "sha256:6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b"
    insecure

    url = "http://example.com/file/2"
    output = "sha256:d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35"
    cacert = "some-ssl_ca_cert"
    no-insecure

    url = "http://example.com/file/3"
    output = "sha256:4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce"
    cert = "some-ssl_client_cert"
    key = "some-ssl_client_key"
    no-insecure

    """)


def test_split_items(sources_module):
    # pylint: disable=W0212
    split = sources_module._split_items(TEST_SOURCE_PAIRS, 2)
    assert len(split) == len(TEST_SOURCE_PAIRS) // 2
    for itms in split:
        assert len(itms) == 2

    split = sources_module._split_items(TEST_SOURCE_PAIRS, 99)
    # pylint: disable=W0212
    assert len(split) == len(TEST_SOURCE_PAIRS)
    for itms in split:
        assert len(itms) == 1


@patch("subprocess.run")
def test_curl_download_many_fail(patched_run, tmp_path, sources_module):
    fake_completed_process = subprocess.CompletedProcess(["args"], 91)
    fake_completed_process.stderr = "something bad happend"

    patched_run.return_value = fake_completed_process
    fd = testutil.make_fake_service_fd()
    with patch.object(sources_module, "curl_has_parallel_downloads") as mocked_cpd:
        mocked_cpd.return_value = False
        curl = sources_module.CurlSource.from_args(["--service-fd", str(fd)])
        curl.cache = tmp_path / "curl-cache"
        curl.cache.mkdir(parents=True, exist_ok=True)

        with pytest.raises(RuntimeError) as exp:
            curl.fetch_many(TEST_SOURCE_PAIRS)
        assert str(exp.value) == 'curl error: "something bad happend": error code 91'


@pytest.mark.parametrize("curl_parallel", [True, False])
@patch("subprocess.run")
def test_curl_download_many(mocked_run, tmp_path, sources_module, curl_parallel):
    def _fake_download(*args, **kwargs):
        download_dir = pathlib.Path(kwargs["cwd"])
        for desc in TEST_SOURCE_PAIRS:
            chksum = desc["checksum"]
            (download_dir / chksum).write_text(desc["url"][-1], encoding="utf8")
        return subprocess.CompletedProcess(args, 0)
    mocked_run.side_effect = _fake_download
    fd = testutil.make_fake_service_fd()
    with patch.object(sources_module, "curl_has_parallel_downloads") as mocked_cpd:
        mocked_cpd.return_value = curl_parallel
        curl = sources_module.CurlSource.from_args(["--service-fd", str(fd)])
        curl.cache = tmp_path / "curl-cache"
        curl.cache.mkdir(parents=True, exist_ok=True)

        curl.fetch_many(TEST_SOURCE_PAIRS)
    for desc in TEST_SOURCE_PAIRS:
        chksum = desc["checksum"]
        assert (curl.cache / chksum).exists()
        assert verify_file(curl.cache / chksum, chksum)
    # check that --parallel is used
    assert len(mocked_run.call_args_list) == 1
    args, _ = mocked_run.call_args_list[0]
    assert ("--parallel" in args[0]) == curl_parallel


# fc39
NEW_CURL_OUTPUT = """\
curl 8.2.1 (x86_64-redhat-linux-gnu) libcurl/8.2.1 OpenSSL/3.1.1 zlib/1.2.13 libidn2/2.3.7 nghttp2/1.55.1
Release-Date: 2023-07-26
Protocols: file ftp ftps http https
Features: alt-svc AsynchDNS GSS-API HSTS HTTP2 HTTPS-proxy IDN IPv6 Kerberos Largefile libz SPNEGO SSL threadsafe UnixSockets
"""

# centos-stream8
OLD_CURL_OUTPUT = """\
curl 7.61.1 (x86_64-redhat-linux-gnu) libcurl/7.61.1 OpenSSL/1.1.1k zlib/1.2.11 nghttp2/1.33.0
Release-Date: 2018-09-05
Protocols: dict file ftp ftps gopher http https imap imaps pop3 pop3s rtsp smb smbs smtp smtps telnet tftp
Features: AsynchDNS IPv6 Largefile GSS-API Kerberos SPNEGO NTLM NTLM_WB SSL libz TLS-SRP HTTP2 UnixSockets HTTPS-proxy
"""


@patch("subprocess.check_output")
def test_curl_has_parallel_download(mocked_check_output, sources_module):
    mocked_check_output.return_value = NEW_CURL_OUTPUT
    assert sources_module.curl_has_parallel_downloads()

    mocked_check_output.return_value = OLD_CURL_OUTPUT
    assert not sources_module.curl_has_parallel_downloads()
