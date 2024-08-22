#!/usr/bin/python3

import os.path
import subprocess
from unittest import mock

import pytest

from osbuild import testutil
from osbuild.testutil import has_executable

STAGE_NAME = "org.osbuild.mkfs.fat"


# Prepare dataset containing good and bad API call parameters
@pytest.mark.parametrize("test_data, expected_err", [
    # Bad API parameters
    ({}, "'volid' is a required property"),
    ({"volid": 123}, "123 is not of type 'string'"),
    ({"volid": "2e24ec82", "label": "12345678901234567"}, "is too long"),
    ({"volid": "2e24ec82", "fat-size": 11}, "11 is not one of [12, 16, 32]"),
    ({"volid": "2e24ec82", "geometry": "text"}, "'text' is not of type 'object'"),
    # Good API parameters
    ({"volid": "2e24ec82", "label": "12345678901"}, ""),
    ({"volid": "2e24ec82", "label": "label", "fat-size": 32}, ""),
    # mkfs requires valid volume ID, but API will accept any string right now.
    # Bellow will fail when API will be more restricted in the future.
    ({"volid": "volumeid"}, ""),
])
# This test validates only API calls using correct and incorrect queries
def test_schema_validation_mkfs_fat(stage_schema, test_data, expected_err):
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
@pytest.mark.skipif(not has_executable("mkfs.fat"), reason="need mkfs.fat")
def test_mkfs_fat_integration(tmp_path, stage_module):
    fake_disk_path = tmp_path / "fake.img"
    with fake_disk_path.open("w") as fp:
        fp.truncate(10 * 1024 * 1024)
    devices = {
        "device": {
            "path": fake_disk_path,
        },
    }
    fake_volid = "2e24ec82"
    fake_label = "osbuild"
    fat_size = 32
    options = {
        "volid": fake_volid,
        "label": fake_label,
        "fat-size": fat_size,
    }
    stage_module.main(devices, options)
    assert os.path.exists(fake_disk_path)
    output = subprocess.check_output([
        "file", "-s", fake_disk_path], encoding="utf-8")
    assert f'serial number 0x{fake_volid}' in output, \
        f'expected serial number (volid) not found in: {output}'
    assert f'label: "{fake_label}    "' in output, \
        f'expected label not found in: {output}'
    assert f'FAT ({fat_size} bit)' in output, \
        f'expected FAT size not found in: {output}'


@pytest.mark.parametrize("test_input, expected", [
    ({}, []),
    ({"fat-size": 32}, ["-F", "32"]),
    ({"fat-size": 16}, ["-F", "16"]),
    ({"fat-size": 12}, ["-F", "12"]),
    ({"label": "osbuild"}, ["-n", "osbuild"]),
    ({"geometry": {"heads": 255, "sectors-per-track": 63}}, ["-g", "255/63"]),
])
@mock.patch("subprocess.run")
def test_mkfs_fat_cmdline(mock_run, stage_module, test_input, expected):
    fake_disk_path = "/dev/xxd1"
    devices = {
        "device": {
            "path": fake_disk_path,
        },
    }
    fake_volid = "2e24ec82"
    options = {
        "volid": fake_volid,
    }
    options.update(test_input)
    stage_module.main(devices, options)

    expected = [
        "mkfs.fat",
        "-I",
        "-i", fake_volid,
    ] + expected + [
        fake_disk_path,
    ]
    mock_run.assert_called_once_with(expected, encoding="utf8", check=True)
