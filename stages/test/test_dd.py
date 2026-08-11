#!/usr/bin/python3

import os
from unittest import mock

import pytest

from osbuild import testutil
from osbuild.testutil import make_fake_input_tree

STAGE_NAME = "org.osbuild.dd"


def make_fake_args(tmp_path, input_tree, input_name="image"):
    return {
        "tree": str(tmp_path / "tree"),
        "inputs": {
            input_name: {
                "path": input_tree,
                "data": {
                    "files": {},
                },
            },
        },
    }


@mock.patch("subprocess.run")
def test_dd_basic(mock_run, tmp_path, stage_module):
    tree = tmp_path / "tree"
    tree.mkdir()

    input_tree = make_fake_input_tree(tmp_path, {
        "/disk.img": "x" * 4096,
    })

    args = make_fake_args(tmp_path, input_tree)

    stage_module.main(args, {
        "src": "input://image/disk.img",
        "dst": "partition.raw",
        "count": 1024,
    })

    mock_run.assert_called_once_with([
        "dd",
        f"if={os.path.join(input_tree, 'disk.img')}",
        f"of={os.path.join(tree, 'partition.raw')}",
        "bs=4096",
        "skip=0",
        "count=1024",
        "iflag=skip_bytes,count_bytes",
        "conv=notrunc",
    ], check=True)


@mock.patch("subprocess.run")
def test_dd_with_offset(mock_run, tmp_path, stage_module):
    tree = tmp_path / "tree"
    tree.mkdir()

    input_tree = make_fake_input_tree(tmp_path, {
        "/disk.img": "x" * 4096,
    })

    args = make_fake_args(tmp_path, input_tree)

    stage_module.main(args, {
        "src": "input://image/disk.img",
        "dst": "partition.raw",
        "src_offset": 2048,
        "count": 1024,
    })

    mock_run.assert_called_once_with([
        "dd",
        f"if={os.path.join(input_tree, 'disk.img')}",
        f"of={os.path.join(tree, 'partition.raw')}",
        "bs=4096",
        "skip=2048",
        "count=1024",
        "iflag=skip_bytes,count_bytes",
        "conv=notrunc",
    ], check=True)


@mock.patch("subprocess.run")
def test_dd_tree_src(mock_run, tmp_path, stage_module):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "disk.img").write_bytes(b"\x00" * 4096)

    args = {"tree": str(tree), "inputs": {}}

    stage_module.main(args, {
        "src": "tree:///disk.img",
        "dst": "partition.raw",
        "count": 512,
    })

    mock_run.assert_called_once_with([
        "dd",
        f"if={os.path.join(tree, 'disk.img')}",
        f"of={os.path.join(tree, 'partition.raw')}",
        "bs=4096",
        "skip=0",
        "count=512",
        "iflag=skip_bytes,count_bytes",
        "conv=notrunc",
    ], check=True)


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({"extra": "option"}, "'extra' was unexpected"),
    ({"count": -1}, "-1 is less than the minimum"),
    ({"count": 0}, "0 is less than the minimum"),
    ({"src_offset": -1}, "-1 is less than the minimum"),
    ({"src": "bad://no/scheme"}, "does not match"),
    # good
    ({}, ""),
    ({"src_offset": 0}, ""),
    ({"src_offset": 1048576}, ""),
])
def test_schema_validation_dd(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": {
            "src": "input://image/disk.img",
            "dst": "partition.raw",
            "count": 1024,
        }
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


@pytest.mark.parametrize("test_data,expected_err", [
    ({"dst": "out.raw", "count": 512}, "'src' is a required property"),
    ({"src": "input://image/disk.img", "count": 512}, "'dst' is a required property"),
    ({"src": "input://image/disk.img", "dst": "out.raw"}, "'count' is a required property"),
])
def test_schema_required_fields(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": test_data,
    }
    res = stage_schema.validate(test_input)
    assert res.valid is False
    testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)
