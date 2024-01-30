#!/usr/bin/python3

import os.path
import re
import subprocess
from unittest import mock

import pytest

from osbuild import testutil
from osbuild.testutil import has_executable

STAGE_NAME = "org.osbuild.mkfs.ext4"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({}, "'uuid' is a required property"),
    ({"uuid": 123}, "123 is not of type 'string'"),
    ({"uuid": "vaild", "label": "12345678901234567"}, " is too long"),
    ({"uuid": "valid", "verity": "please"}, "'please' is not of type 'boolean'"),
    # good
    ({"uuid": "some", "label": "1234567890123456"}, ""),
    ({"uuid": "some", "label": "label", "verity": True}, ""),
    # actually "some-uuid" will not be accepted by mkfs, it has to be a valid
    # uuid but our schema is not strict enough right now
    ({"uuid": "some-uuid"}, ""),
])
def test_schema_validation_mkfs_ext4(stage_schema, test_data, expected_err):
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


@pytest.mark.skipif(not has_executable("mkfs.ext4"), reason="need mkfs.ext4")
def test_mkfs_ext4_integration(tmp_path, stage_module):
    fake_disk_path = tmp_path / "fake.img"
    with fake_disk_path.open("w"):
        os.truncate(os.fspath(fake_disk_path), 10 * 1024 * 1024)
    devices = {
        "device": {
            "path": fake_disk_path,
        },
    }
    fake_uuid = "a957573a-f432-4bed-a0bc-e541bddf8579"
    options = {
        "uuid": fake_uuid,
    }
    stage_module.main(devices, options)
    assert os.path.exists(fake_disk_path)
    output = subprocess.check_output([
        "dumpe2fs", fake_disk_path], encoding="utf-8")
    assert re.search(f"(?ms)Filesystem UUID:\\ +{fake_uuid}", output), \
        f"expected uuid not found in {output}"


@pytest.mark.parametrize("test_input,expected", [
    ({}, []),
    ({"verity": True}, ["-O", "verity"]),
    ({"verity": False}, ["-O", "^verity"]),
    ({"orphan_file": True}, ["-O", "orphan_file"]),
    ({"orphan_file": False}, ["-O", "^orphan_file"]),
    ({"metadata_csum_seed": True}, ["-O", "metadata_csum_seed"]),
    ({"metadata_csum_seed": False}, ["-O", "^metadata_csum_seed"]),
    ({"verity": True, "orphan_file": True, "metadata_csum_seed": True}, ["-O", "verity", "-O", "orphan_file", "-O", "metadata_csum_seed"]),
])
@mock.patch("subprocess.run")
def test_mkfs_ext4_cmdline(mock_run, stage_module, test_input, expected):
    fake_disk_path = "/dev/xxd1"
    devices = {
        "device": {
            "path": fake_disk_path,
        },
    }
    fake_uuid = "a957573a-f432-4bed-a0bc-e541bddf8579"
    options = {
        "uuid": fake_uuid,
    }
    options.update(test_input)
    stage_module.main(devices, options)

    expected = [
        "mkfs.ext4",
        "-U", fake_uuid,
    ] + expected + [
        fake_disk_path,
    ]
    mock_run.assert_called_with(expected, encoding="utf8", check=True)
