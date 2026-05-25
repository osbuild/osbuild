#!/usr/bin/python3
from unittest import mock

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.systemd-repart.create"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({"path": "image.raw"}, "'size' is a required property"),
    ({"size": "1G"}, "'path' is a required property"),
    ({"path": "image.raw", "size": "1G", "seed": 1}, "1 is not of type"),
    ({"path": 1, "size": "1G", "seed": "random"}, "1 is not of type"),
    ({"path": "image.raw", "size": 1, "seed": "random"}, "1 is not of type"),
    # good
    ({"path": "image.raw", "size": "1G"}, ""),
    ({"path": "image.raw", "size": "1G", "seed": "random"}, ""),
])
def test_systemd_repart_create_schema_validation(stage_schema, test_data, expected_err):
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


@mock.patch("subprocess.run")
def test_systemd_repart_create_minimal(mock_run, tmp_path, stage_module):
    fake_tree = tmp_path / "tree"
    fake_root = tmp_path / "root"

    options = {
        "path": "image.raw",
        "size": "1G",
    }

    stage_module.main(
        {
            "tree": fake_tree,
            "inputs": {"root-tree": {"path": str(fake_root)}},
            "options": options,
        },
        options,
    )

    mock_run.assert_called_with([
        "systemd-repart",
        "--empty", "create",
        "--size", "1G",
        "--root", str(fake_root),
        "--seed", "random",
        str(fake_tree / "image.raw"),
    ], check=True)


@mock.patch("subprocess.run")
def test_systemd_repart_create_with_seed(mock_run, tmp_path, stage_module):
    fake_tree = tmp_path / "tree"
    fake_root = tmp_path / "root"

    options = {
        "path": "disk.img",
        "size": "10G",
        "seed": "abc123",
    }

    stage_module.main(
        {
            "tree": fake_tree,
            "inputs": {"root-tree": {"path": str(fake_root)}},
            "options": options,
        },
        options,
    )

    mock_run.assert_called_with([
        "systemd-repart",
        "--empty", "create",
        "--size", "10G",
        "--root", str(fake_root),
        "--seed", "abc123",
        str(fake_tree / "disk.img"),
    ], check=True)
