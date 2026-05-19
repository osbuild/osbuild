#!/usr/bin/python3

import os
import subprocess
import tempfile

import pytest

from osbuild.testutil import has_executable, make_container

INPUTS_NAME = "org.osbuild.containers-storage"


class FakeStoreClient:
    def __init__(self, fake_sources_base):
        self.fake_sources_base = fake_sources_base
        self.fake_sources_base.mkdir()

    def source(self, name: str) -> str:
        fake_source_path = self.fake_sources_base / f"path-for-{name}"
        fake_source_path.mkdir(parents=True)
        return fake_source_path


@pytest.mark.skipif(not has_executable("podman"), reason="no podman executable")
@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_containers_local_inputs_integration(tmp_path, inputs_service):
    with make_container(tmp_path, {"file1": "file1 content"}) as base_tag:
        image_id = subprocess.check_output(
            ["podman", "inspect", "-f", "{{ .Id }}", base_tag],
            universal_newlines=True).strip()
        inputs = {
            "type": INPUTS_NAME,
            "origin": "org.osbuild.source",
            "references": {
                f"sha256:{image_id}": {
                    "name": "localhost/some-name:latest",
                }
            }
        }
        store = FakeStoreClient(tmp_path / "fake-sources")
        # not using "tmp_path" here as it will "rm -rf" on cleanup and
        # that is dangerous as during the tests we bind mount the
        # system container storage read-write
        with tempfile.TemporaryDirectory("cnt-target") as target:
            data, binds = inputs_service.map(store, inputs["origin"], inputs["references"], target, None)
            assert len(data["archives"]) == 1
            assert len(binds) == 1
            assert binds[0][1] == "storage"
