#!/usr/bin/python3

import gzip
import os
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
    ({"path": "/boot/initramfs-5.14.0-247.el9.x86_64.img"}, ""),
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


# This test creates a compressed dummy file then decompresses and
# compares the content.
@pytest.mark.skipif(not has_executable("gunzip"), reason="gunzip")
def test_gunzip_integration(tmp_path, stage_module):
    fake_tree = tmp_path / "fake/output/tree"
    fake_tree.mkdir(parents=True)
    fake_archive_path = fake_tree / "some-file.gz"
    fake_file_content = b"Some random text written to a file"

    with gzip.GzipFile(fake_archive_path, "w") as fp:
        fp.write(fake_file_content)

    inp = {
        "file": {
            "path": fake_tree,
            "data": {
                "files": {
                    fake_archive_path.name: "Some test file"
                }
            },
        },
    }
    expected_output_path = fake_tree / "tree" / "output.txt"
    expected_output_path.parent.mkdir()
    options = {
        "path": expected_output_path.name
    }
    stage_module.main(inp, expected_output_path.parent, options)
    assert expected_output_path.read_bytes() == fake_file_content


# This test evaluates final binary call and match between its flags and stage args
@mock.patch("subprocess.run")
def test_gunzip_cmdline(mock_run, tmp_path, stage_module):
    fake_tree = tmp_path / "fake/output/tree"
    fake_tree.mkdir(parents=True)
    fake_file = "fake_file.txt"
    fake_archive = f"{fake_file}.gz"

    inp = {
        "file": {
            "path": fake_tree,
            "data": {
                "files": {
                    fake_archive: "Some test file"
                }
            },
        },
    }
    options = {
        "path": fake_file
    }
    output = fake_tree
    stage_module.main(inp, output, options)

    expected = [
        "gunzip",
        "--stdout",
    ] + [os.fspath(fake_tree / fake_archive)]
    mock_run.assert_called_once_with(expected, stdout=mock.ANY, check=True)
