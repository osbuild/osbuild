#!/usr/bin/python3

import os
import re

import pytest

from osbuild.testutil import assert_jsonschema_error_contains

STAGE_NAME = "org.osbuild.ln"


def test_ln_symbolic(tmp_path, stage_module):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "target1").touch()
    (tree / "target2").touch()
    (tree / "dir").mkdir()
    (tree / "dir" / "target3").touch()

    options = {
        "paths": [
            {
                "target": "target1",
                "link_name": "tree:///link1",
                "symbolic": True
            },
            {
                "target": "target2",
                "link_name": "tree:///dir/link2",
                "symbolic": True
            },
            {
                "target": "/etc/os-release",
                "link_name": "tree:///os-release",
                "symbolic": True
            }
        ],
    }

    args = {
        "tree": os.fspath(tree)
    }

    stage_module.main(args, options)

    assert os.path.islink(tree / "link1")
    assert os.readlink(tree / "link1") == "target1"
    assert os.path.islink(tree / "dir/link2")
    assert os.readlink(tree / "dir/link2") == "target2"
    assert os.path.islink(tree / "os-release")
    assert os.readlink(tree / "os-release") == "/etc/os-release"


def test_ln_hardlink(tmp_path, stage_module):
    tree = tmp_path / "tree"
    tree.mkdir()
    target_path = tree / "target"
    target_path.write_text("content")

    options = {
        "paths": [
            {
                "target": "target",
                "link_name": "tree:///link",
                "symbolic": False
            }
        ],
    }

    args = {
        "tree": os.fspath(tree)
    }

    old_cwd = os.getcwd()
    os.chdir(tree)
    try:
        stage_module.main(args, options)
    finally:
        os.chdir(old_cwd)

    link_path = tree / "link"
    assert link_path.exists()
    assert not link_path.is_symlink()
    assert target_path.stat().st_ino == link_path.stat().st_ino


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({}, "'paths' is a required property"),
    ({"paths": [{"link_name": "a", "target": "b"}]}, "is not valid under any of the given schemas"),
    ({"paths": "not-an-array"}, "'not-an-array' is not of type 'array'"),
    ({"paths": []}, re.compile(r"\[\] should be non-empty|\[\] is too short")),
    ({"paths": [{"target": "b"}]}, "'link_name' is a required property",),
    ({"paths": [{"link_name": "tree:///a"}]}, "'target' is a required property"),
    ({"paths": [{"link_name": "tree:///a", "target": "b", "symbolic": "not-a-bool"}]},
     "'not-a-bool' is not of type 'boolean'"),
    # good
    ({"paths": [{"link_name": "tree:///a", "target": "b"}]}, ""),
    ({"paths": [{"link_name": "tree:///a", "target": "b", "symbolic": True}]}, ""),
    ({"paths": [{"link_name": "mount://root/a", "target": "b", "symbolic": False}]}, ""),
])
def test_schema_validation(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": {},
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)
