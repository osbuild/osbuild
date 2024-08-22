#!/usr/bin/python3

import os.path
import subprocess
import uuid
from unittest import mock

import pytest

from osbuild import testutil
from osbuild.testutil import has_executable

STAGE_NAME = "org.osbuild.mkfs.xfs"


# Prepare dataset containing good and bad API call parameters
@pytest.mark.parametrize("test_data, expected_err", [
    # Bad API parameters
    ({}, "'uuid' is a required property"),
    ({"uuid": 123}, "123 is not of type 'string'"),
    ({"uuid": "text", "label": 1234}, "1234 is not of type 'string'"),
    ({"uuid": "text", "label": "12345678901234567"}, "is too long"),
    # Good API parameters
    # mkfs requires valid UUID, but API will accept any string right now.
    # Bellow will fail when API will be more restricted in the future.
    ({"uuid": "text"}, ""),
    ({"uuid": "text", "label": "123456789012"}, ""),
])
# This test validates only API calls using correct and incorrect queries
def test_schema_validation_mkfs_xfs(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "devices": {
            "device": {
                "path": "some-path",
            },
        },
        "options": {
        }
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


# This test creates dummy filesystem using predefined parameters and verifies
# that end result has those parameters set
@pytest.mark.skipif(not has_executable("mkfs.xfs"), reason="need mkfs.xfs")
def test_mkfs_xfs_integration(tmp_path, stage_module):
    fake_disk_path = tmp_path / "fake.img"
    with fake_disk_path.open("w") as fp:
        fp.truncate(300 * 1024 * 1024)
    devices = {
        "device": {
            "path": fake_disk_path,
        },
    }
    fake_uuid = str(uuid.uuid4())
    fake_label = "osbuild"
    options = {
        "uuid": fake_uuid,
        "label": fake_label,
    }
    stage_module.main(devices, options)
    assert os.path.exists(fake_disk_path)
    output = subprocess.check_output([
        "xfs_admin", "-l", "-u", fake_disk_path], encoding="utf-8")
    assert f'UUID = {fake_uuid}' in output, \
        f'expected UUID not found in: {output}'
    assert f'label = "{fake_label}"' in output, \
        f'expected label not found in: {output}'


@pytest.mark.parametrize("test_input, expected", [
    ({}, []),
    ({"label": "osbuild"}, ["-L", "osbuild"]),
])
@mock.patch("subprocess.run")
def test_mkfs_xfs_cmdline(mock_run, stage_module, test_input, expected):
    fake_disk_path = "/dev/xxd1"
    devices = {
        "device": {
            "path": fake_disk_path,
        },
    }
    fake_uuid = str(uuid.uuid4())
    options = {
        "uuid": fake_uuid,
    }
    options.update(test_input)
    stage_module.main(devices, options)

    expected = [
        "mkfs.xfs",
        "-m",
        f"uuid={fake_uuid}",
    ] + expected + [
        fake_disk_path,
    ]
    mock_run.assert_called_once_with(expected, encoding="utf8", check=True)
