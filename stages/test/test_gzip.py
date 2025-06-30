#!/usr/bin/python3

import os.path
import subprocess
from unittest import mock

import pytest

from osbuild import testutil
from osbuild.testutil import has_executable, make_fake_input_tree

STAGE_NAME = "org.osbuild.gzip"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({}, "'filename' is a required property"),
    # good
    ({"filename": "image.gz"}, ""),
])
def test_schema_validation_gzip(stage_schema, test_data, expected_err):
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


@pytest.fixture(name="fake_input_tree")
def fake_input(tmp_path):
    fake_input_tree = make_fake_input_tree(tmp_path, {
        "/sha256:ff3e910ceb79fd66e67b7ff4a9073b1d584c748a5f3d1e6b1873afa1cf35ec59": "A file to be compressed",
    })
    inputs = {
        "file": {
            "path": fake_input_tree,
            "data": {
                "files": {
                    "sha256:ff3e910ceb79fd66e67b7ff4a9073b1d584c748a5f3d1e6b1873afa1cf35ec59": {}
                }
            }
        }
    }
    return (fake_input_tree, inputs)


@pytest.mark.skipif(not has_executable("gzip"), reason="no gzip executable")
def test_gzip_integration(tmp_path, stage_module, fake_input_tree):  # pylint: disable=unused-argument
    inputs = fake_input_tree[1]
    options = {
        "filename": "image.txt.gz",
    }
    stage_module.main(inputs, tmp_path, options)

    img_path = os.path.join(tmp_path, "image.txt.gz")
    assert os.path.exists(img_path)
    output = subprocess.check_output([
        "gzip", "--decompress", "--stdout", img_path], encoding="utf-8")
    assert "A file to be compressed" in output


@mock.patch("subprocess.run")
def test_gzip_cmdline(mock_run, tmp_path, stage_module, fake_input_tree):
    fake_input_path = fake_input_tree[0]
    inputs = fake_input_tree[1]
    filename = "image.txt.gz"
    options = {
        "filename": filename,
    }
    stage_module.main(inputs, tmp_path, options)

    expected = [
        "gzip",
        "--keep",
        "--stdout",
        "-6",
        os.path.join(fake_input_path, "sha256:ff3e910ceb79fd66e67b7ff4a9073b1d584c748a5f3d1e6b1873afa1cf35ec59")
    ]
    mock_run.assert_called_with(expected, stdout=mock.ANY, check=True)
