#!/usr/bin/python3

import os.path
from unittest.mock import call, patch

import pytest

import osbuild.meta
from osbuild import testutil
from osbuild.testutil.imports import import_module_from_path


def schema_validation_selinux(test_data, implicit_file_contexts=True):
    name = "org.osbuild.selinux"
    root = os.path.join(os.path.dirname(__file__), "../..")
    mod_info = osbuild.meta.ModuleInfo.load(root, "Stage", name)
    schema = osbuild.meta.Schema(mod_info.get_schema(version="1"), name)

    test_input = {
        "name": "org.osbuild.selinux",
        "options": {}
    }
    if implicit_file_contexts:
        test_input["options"]["file_contexts"] = "some-context"

    test_input["options"].update(test_data)
    return schema.validate(test_input)


@pytest.mark.parametrize("test_data,expected_err", [
    # good
    ({"labels": {"/usr/bin/cp": "system_u:object_r:install_exec_t:s0"}}, ""),
    ({"force_autorelabel": True}, ""),
    # bad
    ({"file_contexts": 1234}, "1234 is not of type 'string'"),
    ({"labels": "xxx"}, "'xxx' is not of type 'object'"),
    ({"force_autorelabel": "foo"}, "'foo' is not of type 'boolean'"),
])
def test_schema_validation_selinux(test_data, expected_err):
    res = schema_validation_selinux(test_data)
    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


def test_schema_validation_selinux_file_context_required():
    test_data = {}
    res = schema_validation_selinux(test_data, implicit_file_contexts=False)
    assert res.valid is False
    expected_err = "'file_contexts' is a required property"
    testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


@patch("osbuild.util.selinux.setfiles")
def test_selinux_file_contexts(mocked_setfiles, tmp_path):
    stage_path = os.path.join(os.path.dirname(__file__), "../org.osbuild.selinux")
    stage = import_module_from_path("stage", stage_path)

    options = {
        "file_contexts": "etc/selinux/thing",
    }
    stage.main(tmp_path, options)

    assert len(mocked_setfiles.call_args_list) == 1
    assert mocked_setfiles.call_args_list == [
        call(f"{tmp_path}/etc/selinux/thing", os.fspath(tmp_path), "")
    ]


@patch("osbuild.util.selinux.setfilecon")
@patch("osbuild.util.selinux.setfiles")
def test_selinux_labels(mocked_setfiles, mocked_setfilecon, tmp_path):
    stage_path = os.path.join(os.path.dirname(__file__), "../org.osbuild.selinux")
    stage = import_module_from_path("stage", stage_path)

    osbuild.testutil.make_fake_input_tree(tmp_path, {
        "/usr/bin/bootc": "I'm only an imposter",
    })

    options = {
        "file_contexts": "etc/selinux/thing",
        "labels": {
            "/tree/usr/bin/bootc": "system_u:object_r:install_exec_t:s0",
        }
    }
    stage.main(tmp_path, options)

    assert len(mocked_setfiles.call_args_list) == 1
    assert len(mocked_setfilecon.call_args_list) == 1
    assert mocked_setfilecon.call_args_list == [
        call(f"{tmp_path}/tree/usr/bin/bootc", "system_u:object_r:install_exec_t:s0"),
    ]


@patch("osbuild.util.selinux.setfiles")
def test_selinux_force_autorelabel(mocked_setfiles, tmp_path):  # pylint: disable=unused-argument
    stage_path = os.path.join(os.path.dirname(__file__), "../org.osbuild.selinux")
    stage = import_module_from_path("stage", stage_path)

    for enable_autorelabel in [False, True]:
        options = {
            "file_contexts": "etc/selinux/thing",
            "force_autorelabel": enable_autorelabel,
        }
        stage.main(tmp_path, options)

        assert (tmp_path / ".autorelabel").exists() == enable_autorelabel
