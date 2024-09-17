#!/usr/bin/python3

import os.path
import subprocess

import pytest

from osbuild import testutil
from osbuild.testutil import has_executable, make_fake_input_tree

STAGE_NAME = "org.osbuild.tar"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({}, "'filename' is a required property"),
    ({
        "filename": "out.tar",
        "root-node": "include",
        "paths": ["file1"]
    }, "{'filename': 'out.tar', 'root-node': 'include', 'paths': ['file1']} is not valid under any of the given schemas"),
    ({
        "filename": "foo",
        "transform": ["transform-cannot-be-passed-multiple-times"],
    }, " is not of type 'string'"),
    # good
    ({"filename": "out.tar", "root-node": "include"}, ""),
    ({"filename": "out.tar", "paths": ["file1"]}, ""),
    ({"filename": "out.tar", "sparse": True}, ""),
    ({"filename": "out.tar"}, ""),
    ({"filename": "out.tar", "transform": "s/foo/bar"}, ""),
])
def test_schema_validation_tar(stage_schema, test_data, expected_err):
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


@pytest.fixture(name="fake_inputs")
def make_fake_inputs(tmp_path):
    fake_input_tree = make_fake_input_tree(tmp_path, {
        "/file1": "A file to be tarred",
        "/file2": "Another file to be tarred",
    })
    inputs = {
        "tree": {
            "path": fake_input_tree,
        }
    }
    return inputs


@pytest.mark.skipif(not has_executable("tar"), reason="no tar executable")
def test_tar_filename(tmp_path, stage_module, fake_inputs):
    options = {
        "filename": "out.tar",
    }
    stage_module.main(fake_inputs, tmp_path, options)

    tar_path = os.path.join(tmp_path, "out.tar")
    assert os.path.exists(tar_path)
    output = subprocess.check_output(["tar", "-tf", tar_path], encoding="utf-8").strip().split("\n")
    assert sorted(["./", "./file1", "./file2"]) == sorted(output)


@pytest.mark.skipif(not has_executable("tar"), reason="no tar executable")
def test_tar_root_node_omit(tmp_path, stage_module, fake_inputs):
    options = {
        "filename": "out.tar",
        "root-node": "omit",
    }
    stage_module.main(fake_inputs, tmp_path, options)

    tar_path = os.path.join(tmp_path, "out.tar")
    assert os.path.exists(tar_path)
    output = subprocess.check_output(["tar", "-tf", tar_path], encoding="utf-8").strip().split("\n")
    assert sorted(["file1", "file2"]) == sorted(output)


@pytest.mark.skipif(not has_executable("tar"), reason="no tar executable")
def test_tar_paths(tmp_path, stage_module, fake_inputs):
    options = {
        "filename": "out.tar",
        "paths": [
            "file2",
            "file1",
            "file1",
            "file2",
        ]
    }
    stage_module.main(fake_inputs, tmp_path, options)

    tar_path = os.path.join(tmp_path, "out.tar")
    assert os.path.exists(tar_path)
    output = subprocess.check_output(["tar", "-tf", tar_path], encoding="utf-8").split("\n")
    assert ["file2", "file1", "file1", "file2", ""] == output


@pytest.mark.skipif(not has_executable("tar"), reason="no tar executable")
@pytest.mark.parametrize("transform,expected_tar_output", [
    # unrelated transform
    ("s/foo/bar/", ["file1", "file2", ""]),
    # one file
    ("s/^file1$/foo99/", ["foo99", "file2", ""]),
    # one file
    ("s/file1/foo99/;s/file2/bar11/", ["foo99", "bar11", ""]),
])
def test_tar_transform(tmp_path, stage_module, fake_inputs, transform, expected_tar_output):
    options = {
        "filename": "out.tar",
        "paths": [
            "file1",
            "file2",
        ],
        "transform": transform,
    }
    stage_module.main(fake_inputs, tmp_path, options)

    tar_path = os.path.join(tmp_path, "out.tar")
    assert os.path.exists(tar_path)
    output = subprocess.check_output(["tar", "-tf", tar_path], encoding="utf-8").split("\n")
    assert output == expected_tar_output


def test_tar_transform_no_sh(tmp_path, stage_module, fake_inputs):
    options = {
        "filename": "out.tar",
        "paths": [
            "file1",
        ],
        # GNU sed allows to run shell commands with "/e"
        # ensure here we donot allow this
        "transform": "s/file1/date/e",
    }
    with pytest.raises(subprocess.CalledProcessError) as ex:
        stage_module.main(fake_inputs, tmp_path, options)
    assert "exit status 2" in str(ex.value)
