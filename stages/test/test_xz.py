#!/usr/bin/python3

import os.path
import subprocess
from unittest import mock

import pytest

import osbuild.meta
from osbuild.testutil import has_executable, make_fake_input_tree
from osbuild.testutil.imports import import_module_from_path


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({}, "'filename' is a required property"),
    # good
    ({"filename": "image.xz"}, ""),
])
def test_schema_validation_xz(test_data, expected_err):
    name = "org.osbuild.xz"
    root = os.path.join(os.path.dirname(__file__), "../..")
    mod_info = osbuild.meta.ModuleInfo.load(root, "Stage", name)
    schema = osbuild.meta.Schema(mod_info.get_schema(version="2"), name)

    test_input = {
        "type": "org.osbuild.xz",
        "options": {
        }
    }
    test_input["options"].update(test_data)
    res = schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        assert len(res.errors) == 1, [e.as_dict() for e in res.errors]
        err_msgs = [e.as_dict()["message"] for e in res.errors]
        assert expected_err in err_msgs[0]


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


@pytest.mark.skipif(not has_executable("xz"), reason="no xz executable")
def test_xz_integration(tmp_path, fake_input_tree):  # pylint: disable=unused-argument
    inputs = fake_input_tree[1]
    stage_path = os.path.join(os.path.dirname(__file__), "../org.osbuild.xz")
    stage = import_module_from_path("xz_stage", stage_path)
    options = {
        "filename": "image.txt.xz",
    }
    stage.main(inputs, tmp_path, options)

    img_path = os.path.join(tmp_path, "image.txt.xz")
    assert os.path.exists(img_path)
    output = subprocess.check_output([
        "xz", "--decompress", "--stdout", img_path], encoding="utf-8")
    assert "A file to be compressed" in output


@mock.patch("subprocess.run")
def test_xz_cmdline(mock_run, tmp_path, fake_input_tree):
    fake_input_path = fake_input_tree[0]
    inputs = fake_input_tree[1]
    stage_path = os.path.join(os.path.dirname(__file__), "../org.osbuild.xz")
    stage = import_module_from_path("xz_stage", stage_path)
    filename = "image.txt.xz"
    options = {
        "filename": filename,
    }
    stage.main(inputs, tmp_path, options)

    expected = [
        "xz",
        "--keep",
        "--stdout",
        "-0",
        os.path.join(fake_input_path, "sha256:ff3e910ceb79fd66e67b7ff4a9073b1d584c748a5f3d1e6b1873afa1cf35ec59")
    ]
    mock_run.assert_called_with(expected, stdout=mock.ANY, check=True, env={'XZ_OPT': '--threads 0'})
