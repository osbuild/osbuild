#!/usr/bin/python3

import re

import pytest

from osbuild.testutil import assert_jsonschema_error_contains

STAGE_NAME = "org.osbuild.grub2.d"


@pytest.mark.parametrize("test_data,expected_err", [
    # good - tree:// paths
    ({"config": {"serial": "serial --speed=115200"}, "path": "tree:///boot/grub2/console.cfg"}, ""),
    ({"config": {"terminal_input": ["serial", "console"]}, "path": "tree:///boot/grub2/console.cfg"}, ""),
    ({"config": {"terminal_output": ["serial", "console"]}, "path": "tree:///boot/grub2/console.cfg"}, ""),
    ({"config": {
        "serial": "serial --speed=115200",
        "terminal_input": ["serial", "console"],
        "terminal_output": ["serial", "console"],
    }, "path": "tree:///boot/grub2/console.cfg"}, ""),
    # good - mount:// paths
    ({"config": {"serial": "serial --speed=115200"}, "path": "mount://root/boot/grub2/custom.cfg"}, ""),
    ({"config": {"serial": "serial --speed=115200"}, "path": "mount://root/etc/grub.d/99-serial.cfg"}, ""),
    # bad - missing required config
    ({"path": "tree:///boot/grub2/console.cfg"}, "'config' is a required property"),
    # bad - missing required path
    ({"config": {"serial": "serial --speed=115200"}}, "'path' is a required property"),
    # bad - empty config
    ({"config": {}, "path": "tree:///boot/grub2/console.cfg"},
     re.compile(r"{} should be non-empty|{} does not have enough properties")),
    # bad - unknown property in config
    ({"config": {"unknown": "value"}, "path": "tree:///boot/grub2/console.cfg"}, "Additional properties are not allowed"),
    # bad - wrong types
    ({"config": {"serial": 123}, "path": "tree:///boot/grub2/console.cfg"}, "123 is not of type 'string'"),
    ({"config": {"terminal_input": "not-an-array"}, "path": "tree:///boot/grub2/console.cfg"},
     "'not-an-array' is not of type 'array'"),
    ({"config": {"terminal_output": "not-an-array"}, "path": "tree:///boot/grub2/console.cfg"},
     "'not-an-array' is not of type 'array'"),
    ({"config": {"terminal_input": [123]}, "path": "tree:///boot/grub2/console.cfg"},
     "123 is not of type 'string'"),
    # bad - unknown top-level option
    ({"config": {"serial": "serial"}, "unknown": "value", "path": "tree:///x"}, "Additional properties are not allowed"),
    # bad - bare path (no scheme)
    ({"config": {"serial": "serial"}, "path": "boot/grub2/console.cfg"}, "is not valid under any of the given schemas"),
    ({"config": {"serial": "serial"}, "path": "/boot/grub2/console.cfg"}, "is not valid under any of the given schemas"),
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
        assert_jsonschema_error_contains(res, expected_err)


@pytest.mark.parametrize("config,expected_lines", [
    # empty config produces empty file
    ({}, []),
    # serial only
    (
        {"serial": "serial --speed=115200"},
        ["serial --speed=115200"],
    ),
    # terminal_input only
    (
        {"terminal_input": ["serial", "console"]},
        ["terminal_input serial console"],
    ),
    # terminal_output only
    (
        {"terminal_output": ["serial"]},
        ["terminal_output serial"],
    ),
    # all three
    (
        {
            "serial": "serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1",
            "terminal_input": ["serial", "console"],
            "terminal_output": ["serial", "console"],
        },
        [
            "serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1",
            "terminal_input serial console",
            "terminal_output serial console",
        ],
    ),
])
def test_generate_grub2_dropin(tmp_path, stage_module, config, expected_lines):
    dropin_path = tmp_path / "test.cfg"
    stage_module.generate_grub2_dropin(config, dropin_path)

    content = dropin_path.read_text(encoding="utf8")
    if expected_lines:
        assert content == "\n".join(expected_lines) + "\n"
    else:
        assert content == ""


def test_main_tree_path(tmp_path, stage_module):
    """main() writes to the specified tree:// location."""
    args = {"tree": str(tmp_path)}
    options = {
        "path": "tree:///boot/grub2/console.cfg",
        "config": {
            "serial": "serial --speed=115200",
            "terminal_input": ["serial", "console"],
            "terminal_output": ["serial", "console"],
        },
    }
    stage_module.main(args, options)

    cfg_path = tmp_path / "boot" / "grub2" / "console.cfg"
    assert cfg_path.exists()
    content = cfg_path.read_text(encoding="utf8")
    assert "serial --speed=115200\n" in content
    assert "terminal_input serial console\n" in content
    assert "terminal_output serial console\n" in content


def test_main_creates_parent_dirs(tmp_path, stage_module):
    """main() creates parent directories if they don't exist."""
    args = {"tree": str(tmp_path)}
    options = {
        "path": "tree:///boot/grub2/console.cfg",
        "config": {
            "serial": "serial --speed=115200",
        },
    }
    stage_module.main(args, options)

    cfg_path = tmp_path / "boot" / "grub2" / "console.cfg"
    assert cfg_path.exists()
