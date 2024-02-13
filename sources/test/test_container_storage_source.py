#!/usr/bin/python3

import os
import random
import socket
import string
import subprocess

import pytest

from osbuild.testutil import has_executable, make_container

SOURCES_NAME = "org.osbuild.containers-storage"


@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_containers_storage_integration(tmp_path, sources_module):
    base_tag = "container-" + "".join(random.choices(string.digits, k=12))
    make_container(tmp_path, base_tag, {
        "file1": "file1 content",
    })
    image_id = subprocess.check_output(["podman", "inspect", "-f", "{{ .Id }}", base_tag],
                                       universal_newlines=True).strip()
    checksum = f"sha256:{image_id}"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    cnt_storage = sources_module.ContainersStorageSource.from_args(["--service-fd", str(sock.fileno())])
    assert cnt_storage.exists(checksum, None)
