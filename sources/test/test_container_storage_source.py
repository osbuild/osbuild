#!/usr/bin/python3

import os
import socket
import subprocess

import pytest

from osbuild.testutil import has_executable, make_container

SOURCES_NAME = "org.osbuild.containers-storage"


@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_containers_storage_integration(tmp_path, sources_module):
    with make_container(tmp_path, {
        "file1": "file1 content",
    }) as base_tag:
        image_id = subprocess.check_output(["podman", "inspect", "-f", "{{ .Id }}", base_tag],
                                           universal_newlines=True).strip()
        checksum = f"sha256:{image_id}"
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        cnt_storage = sources_module.ContainersStorageSource.from_args(["--service-fd", str(sock.fileno())])
        assert cnt_storage.exists(checksum, None)


@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_containers_storage_integration_missing(sources_module):
    checksum = "sha256:1234567890123456789012345678901234567890909b14ffb032aa20fa23d9ad6"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    cnt_storage = sources_module.ContainersStorageSource.from_args(["--service-fd", str(sock.fileno())])
    assert not cnt_storage.exists(checksum, None)


@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_containers_storage_integration_invalid(sources_module):
    # put an invalid reference into the source to ensure skopeo errors with
    # a different error than image not found
    checksum = "sha256:["
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    cnt_storage = sources_module.ContainersStorageSource.from_args(["--service-fd", str(sock.fileno())])
    with pytest.raises(RuntimeError) as exc:
        cnt_storage.exists(checksum, None)
    assert "unknown skopeo error:" in str(exc)
