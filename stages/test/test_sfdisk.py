#!/usr/bin/python3

import os.path
import subprocess
from unittest import mock

import pytest

from osbuild import testutil
from osbuild.testutil import has_executable

STAGE_NAME = "org.osbuild.sfdisk"


@pytest.mark.skipif(not has_executable("sfdisk"), reason="no sfdisk executable")
@pytest.mark.skipif(not has_executable("sgdisk"), reason="no sgfdisk executable")
def test_sfdisk_rhel_105254(tmp_path, stage_module):
    # generated with "image-builder manifest --distro rhel-10 qcow2"
    options = {
        "label": "gpt",
        "uuid": "D209C89E-EA5E-4FBD-B161-B461CCE297E0",
        "partitions": [
              {
                  "bootable": True,
                "size": 2048,
                "start": 2048,
                "type": "21686148-6449-6E6F-744E-656564454649",
                "uuid": "FAC7F1FB-3E8D-4137-A512-961DE09A5549"
              },
            {
                  "size": 409600,
                  "start": 4096,
                  "type": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
                "uuid": "68B2905B-DF3E-4FB3-80FA-49D1E773AA33"
              },
            {
                  "size": 20557791,
                  "start": 413696,
                  "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                "uuid": "6264D520-3FB9-423F-8AB8-7A0A8E3D3562"
              }
        ]
    }
    fake_disk = tmp_path / "test.img"
    fake_disk.write_bytes(b"")
    os.truncate(fake_disk, 10737418240)  # 10 GiB
    devices = {
        "device": {
            "path": fake_disk,
        }
    }

    stage_module.main(devices, options)
    subprocess.check_call(["sgdisk", "-e", fake_disk])
