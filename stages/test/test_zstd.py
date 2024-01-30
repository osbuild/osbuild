#!/usr/bin/python3

import os.path
import subprocess
from unittest import mock

import pytest

import osbuild.meta
from osbuild import testutil
from osbuild.testutil import has_executable, make_fake_input_tree

STAGE_NAME = "org.osbuild.zstd"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({}, "'filename' is a required property"),
    # good
    ({"filename": "image.zst"}, ""),
])
def test_schema_validation_zstd(test_data, expected_err):
    root = os.path.join(os.path.dirname(__file__), "../..")
    mod_info = osbuild.meta.ModuleInfo.load(root, "Stage", STAGE_NAME)
    schema = osbuild.meta.Schema(mod_info.get_schema(version="2"), STAGE_NAME)

    test_input = {
        "type": STAGE_NAME,
        "options": {
        }
    }
    test_input["options"].update(test_data)
    res = schema.validate(test_input)

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


@pytest.mark.skipif(not has_executable("zstd"), reason="no zstd executable")
def test_zstd_integration(tmp_path, stage_module, fake_input_tree):  # pylint: disable=unused-argument
    inputs = fake_input_tree[1]
    options = {
        "filename": "image.txt.zst",
    }
    stage_module.main(inputs, tmp_path, options)

    img_path = os.path.join(tmp_path, "image.txt.zst")
    assert os.path.exists(img_path)
    output = subprocess.check_output([
        "zstd", "--decompress", "--stdout", img_path], encoding="utf-8")
    assert "A file to be compressed" in output


@mock.patch("subprocess.run")
def test_zstd_cmdline(mock_run, tmp_path, stage_module, fake_input_tree):
    fake_input_path = fake_input_tree[0]
    inputs = fake_input_tree[1]
    filename = "image.txt.zst"
    options = {
        "filename": filename,
    }
    stage_module.main(inputs, tmp_path, options)

    expected = [
        "zstd",
        "--keep",
        "--stdout",
        "-T0",
        "-1",
        os.path.join(fake_input_path, "sha256:ff3e910ceb79fd66e67b7ff4a9073b1d584c748a5f3d1e6b1873afa1cf35ec59")
    ]
    mock_run.assert_called_with(expected, stdout=mock.ANY, check=True)
