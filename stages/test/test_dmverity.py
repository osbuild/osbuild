#!/usr/bin/python3

import os
import subprocess

import pytest  # type: ignore

from osbuild import testutil
from osbuild.testutil import has_executable

STAGE_NAME = "org.osbuild.dmverity"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({}, "'root_hash_file' is a required property"),
    ({"root_hash_file": 123}, "123 is not of type 'string'"),
    # good
    ({"root_hash_file": "abc"}, ""),
])
def test_schema_validation_dmverity(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "devices": {
            "data_device": {
                "path": "some-path",
            },
            "hash_device": {
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
@pytest.mark.skipif(not has_executable("veritysetup"), reason="need veritysetup")
def test_dmverity_integration(tmp_path, stage_module):
    fake_dev_path = tmp_path / "dev"
    fake_dev_path.mkdir()

    fake_data_disk = "xxd1"
    fake_hash_disk = "xxd2"
    for fname in [fake_data_disk, fake_hash_disk]:
        p = fake_dev_path / fname
        p.write_bytes(b"")
        os.truncate(p, 10 * 1024 * 1024)
    # format is not strictly needed as dmvertify is working on the block level but this makes the test more realistic
    subprocess.run(
        ["mkfs.ext4", os.fspath(fake_dev_path / fake_data_disk)], check=True)

    paths = {
        "devices": fake_dev_path,
    }
    devices = {
        "data_device": {
            "path": fake_data_disk,
        },
        "hash_device": {
            "path": fake_hash_disk,
        },
    }
    options = {
        "root_hash_file": "hashfile",
    }

    tree = tmp_path
    stage_module.main(tree, paths, devices, options)
    output = subprocess.check_output(
        ["veritysetup", "dump", os.fspath(fake_dev_path / fake_hash_disk)],
        universal_newlines=True)
    assert "UUID:" in output
    # hash file is created and has the expected size
    assert (tree / "hashfile").stat().st_size == 64
