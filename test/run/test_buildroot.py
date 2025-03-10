import json
import os
import subprocess

import pytest

from osbuild.testutil import make_container

# pylint: disable=unused-import
from .test_exports import osbuild_fixture, testing_libdir_fixture  # noqa:F401


@pytest.mark.skipif(os.getuid() != 0, reason="root-only")
def test_build_root_from_container_registry(osb, tmp_path, testing_libdir):
    cnt_ref = "registry.access.redhat.com/ubi9:latest"
    with make_container(tmp_path, {"/usr/bin/buildroot-from-container": "foo"}, cnt_ref) as fake_cnt_tag:
        img_id = subprocess.check_output(["podman", "inspect", "--format={{.Id}}", fake_cnt_tag], text=True).strip()
        jsondata = json.dumps({
            "version": "2",
            "pipelines": [
                {
                    "name": "image",
                    "build": f"org.osbuild.containers-storage:sha256:{img_id}",
                    "stages": [
                        {
                            "type": "org.osbuild.testing.injectpy",
                            "options": {
                                "code": [
                                    'import os.path',
                                    'assert os.path.exists("/usr/bin/buildroot-from-container")',
                                ],
                            },
                        },
                    ],
                },
            ],
            "sources": {
                "org.osbuild.containers-storage": {
                    "items": {
                        f"sha256:{img_id}": {}
                    }
                }
            }
        })
        osb.compile(jsondata, output_dir=tmp_path, exports=["image"], libdir=testing_libdir)
        # ensure no mounts left behind
        mounted = subprocess.check_output(["podman", "image", "mount"], text=True)
        assert fake_cnt_tag not in mounted
