#!/usr/bin/python3

import os.path
import zipfile

import pytest

from osbuild import testutil
from osbuild.testutil import has_executable, make_fake_input_tree

STAGE_NAME = "org.osbuild.zip"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({}, "'filename' is a required property"),
    ({"filename": "x", "level": 99}, "99 is greater than the maximum of 9"),
    # good
    ({"filename": "image.zip"}, ""),
])
def test_schema_validation_zip(stage_schema, test_data, expected_err):
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


@pytest.mark.parametrize("only_include, expected", [
    ([], ["file-in-root.txt", "subdir/", "subdir/subdir.txt", "subdir2/", "subdir2/subdir2.txt"]),
    (["subdir/*"], ["subdir/", "subdir/subdir.txt"]),
    (["subdir/*", "subdir2/*"], ["subdir/", "subdir/subdir.txt", "subdir2/", "subdir2/subdir2.txt"]),
])
@pytest.mark.skipif(not has_executable("zip"), reason="no zip executable")
def test_zip_integration(tmp_path, stage_module, only_include, expected):
    fake_input_tree = make_fake_input_tree(tmp_path, {
        "/file-in-root.txt": "other content",
        "/subdir/subdir.txt": "subdir content",
        "/subdir2/subdir2.txt": "subdir2 content",
    })
    inputs = {
        "tree": {
            "path": fake_input_tree,
        }
    }
    options = {
        "filename": "archive.zip",
    }
    if only_include:
        options["include"] = only_include
    output_dir = tmp_path
    stage_module.main(inputs, output_dir, options)
    expected_zip_path = output_dir / "archive.zip"
    assert os.path.exists(expected_zip_path)
    with zipfile.ZipFile(expected_zip_path, "r") as zfp:
        assert sorted(zfp.namelist()) == sorted(expected)
