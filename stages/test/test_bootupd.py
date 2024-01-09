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
    ({"deployment": "totally"}, "'totally' is not of type 'object'"),
    ({"deployment": {"osname": "some-os"}}, "'ref' is a required property"),
    ({"deployment": {"ref": "some-ref"}}, "'osname' is a required property"),
    ({"deployment": {"osname": "some-os", "ref": "some-ref", "serial": "yo"}}, "'yo' is not of type 'number'"),
    ({"random": "property"}, "Additional properties are not allowed"),
    ({"bios": {}}, "'device' is a required property"),
    ({"bios": "yes"}, "'yes' is not of type 'object'"),
    # good
    ({}, ""),
    ({"deployment": {
          "osname": "some-os",
          "ref": "some-ref",
          "serial": 1,
      },
      "static-configs": True,
      "bios": {
          "device": "/dev/sda",
      }}, "")

])
def test_schema_validation_bootupd(test_data, expected_err):
    name = "org.osbuild.bootupd"
    root = os.path.join(os.path.dirname(__file__), "../..")
    mod_info = osbuild.meta.ModuleInfo.load(root, "Stage", name)
    schema = osbuild.meta.Schema(mod_info.get_schema(version="2"), name)

    test_input = {
        "type": "org.osbuild.bootupd",
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
