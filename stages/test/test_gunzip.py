#!/usr/bin/python3

import os.path
import re
import subprocess
from unittest import mock

import pytest

from osbuild import testutil
from osbuild.testutil import has_executable

STAGE_NAME = "org.osbuild.gunzip"


# Prepare dataset containing good and bad API call parameters
@pytest.mark.parametrize("test_data, expected_err", [
    # Bad API parameters
    ({}, "'path' is a required property"),
    ({"path": 123}, "123 is not of type 'string'"),
    # Good API parameters
    ({"path": "/tmp/"}, ""),
])
# This test validates only API calls using correct and incorrect queries
def test_schema_validation_gunzip(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
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


# This test creates dummy file, compresses it and then decompresses.
# End result checksum is compared with initial file checksum.
@pytest.mark.skipif(not has_executable("gunzip"), reason="gunzip")
@pytest.mark.skipif(not has_executable("gzip"), reason="gzip")
def test_gunzip_integration(tmp_path, stage_module):
    fake_file = "fake_file.txt"
    fake_archive = f"{fake_file}.gz"
    fake_input_path = tmp_path / fake_file

    with fake_input_path.open("w"):
        # Create 10MB file
        os.truncate(os.fspath(fake_input_path), 10 * 1024 * 1024)
    assert os.path.exists(fake_input_path)

    input_checksum = subprocess.check_output([
        "md5sum", fake_input_path], encoding="utf-8")

    output = subprocess.check_output([
        # gzip prints verbouse output on STDERR by default
        "gzip", "-v", fake_input_path], encoding="utf-8", stderr=subprocess.STDOUT)
    assert re.search(f"{fake_archive}", output), \
            f"expect filename: {fake_archive} in: {output}"

    inp = {
        "file": {
            "path": tmp_path,
            "data": {
                "files": {
                    fake_archive: "Some test file"
                }
            },
        },
    }
    output = tmp_path
    options = {
        "path": fake_file
    }
    stage_module.main(inp, output, options)

    output_checksum = subprocess.check_output([
        "md5sum", fake_input_path], encoding="utf-8")
    assert output_checksum == input_checksum, \
           "Input and output files does not match"


@pytest.mark.parametrize("test_input, expected", [
    ({"path": "test_file.txt"}, ["/tmp/test_file.txt.gz"]),
])
# This test evaluates final binary call and match between its flags and stage args
@mock.patch("subprocess.run")
def test_gunzip_cmdline(mock_run, stage_module, test_input, expected):
    tmp_path = "/tmp"
    fake_file = "fake_file.txt"
    fake_archive = f"{fake_file}.gz"
    fake_input_path = tmp_path + "/" + fake_file

    inp = {
        "file": {
            "path": tmp_path,
            "data": {
                "files": {
                    fake_archive: "Some test file"
                }
            },
        },
    }
    options = {
    }
    output = tmp_path
    options.update(test_input)
    stage_module.main(inp, output, options)

    expected = [
        "gunzip",
        "--stdout",
    ] + expected
    mock_run.assert_called_with(expected, encoding="utf8", check=True)

