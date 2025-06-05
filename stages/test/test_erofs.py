#!/usr/bin/python3

import os.path
import subprocess
from unittest import mock

import pytest

from osbuild import testutil
from osbuild.testutil import has_executable, make_fake_input_tree

TEST_INPUT = [
    ({}, []),
    ({"compression": {"method": "lz4"}}, ["-z", "lz4"]),
    ({"compression": {"method": "lz4hc", "level": 9}}, ["-z", "lz4hc,9"]),
    ({"options": ["dedupe"]}, ["-E", "dedupe"]),
    ({"options": ["all-fragments", "force-inode-compact"]}, ["-E", "all-fragments,force-inode-compact"]),
    ({"cluster-size": 131072, "options": ["dedupe"]}, ["-E", "dedupe", "-C", "131072"]),
    ({"exclude_paths": ["boot/", "root/"]}, ["--exclude-regex", "boot/", "--exclude-regex", "root/"])
]


STAGE_NAME = "org.osbuild.erofs"


@pytest.mark.skipif(not has_executable("mkfs.erofs"), reason="no mkfs.erofs")
@pytest.mark.parametrize("test_options,expected", TEST_INPUT)
def test_erofs_integration(tmp_path, stage_module, test_options, expected):  # pylint: disable=unused-argument
    fake_input_tree = make_fake_input_tree(tmp_path, {
        "/file-in-root.txt": "other content",
        "/subdir/file-in-subdir.txt": "subdir content",
    })
    inputs = {
        "tree": {
            "path": fake_input_tree,
        }
    }
    filename = "some-file.img"
    options = {
        "filename": filename,
    }
    options.update(test_options)

    stage_module.main(inputs, tmp_path, options)

    img_path = os.path.join(tmp_path, "some-file.img")
    assert os.path.exists(img_path)
    # validate the content
    output = subprocess.check_output([
        "dump.erofs", "--ls", "--path=/", img_path], encoding="utf-8")
    assert "subdir\n" in output
    assert "file-in-root.txt\n" in output
    output = subprocess.check_output([
        "dump.erofs", "--ls", "--path=/subdir", img_path], encoding="utf-8")
    assert "file-in-subdir.txt\n" in output


@mock.patch("subprocess.run")
@pytest.mark.parametrize("test_options,expected", TEST_INPUT)
def test_erofs(mock_run, tmp_path, stage_module, test_options, expected):
    fake_input_tree = make_fake_input_tree(tmp_path, {
        "/some-dir/some-file.txt": "content",
    })
    inputs = {
        "tree": {
            "path": fake_input_tree,
        }
    }
    filename = "some-file.img"
    options = {
        "filename": filename,
    }
    options.update(test_options)

    stage_module.main(inputs, tmp_path, options)

    expected = [
        "mkfs.erofs",
        f"{os.path.join(tmp_path, filename)}",
        f"{fake_input_tree}",
    ] + expected
    mock_run.assert_called_with(expected, check=True)


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({"extra": "option"}, "'extra' was unexpected"),
    ({"compression": {"method": "invalid"}}, "'invalid' is not one of ["),
    ({"compression": {"method": "lz4", "level": "string"}}, "'string' is not of type "),
    # good
    ({"compression": {"method": "lz4"}}, ""),
])
def test_schema_validation_erofs(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": {
            "filename": "some-filename.img",
        }
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)
