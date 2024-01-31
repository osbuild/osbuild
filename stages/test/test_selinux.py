#!/usr/bin/python3

import os.path
from unittest.mock import call, patch

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.selinux"


def get_test_input(test_data, implicit_file_contexts=True):
    test_input = {
        "name": STAGE_NAME,
        "options": {}
    }
    if implicit_file_contexts:
        test_input["options"]["file_contexts"] = "some-context"

    test_input["options"].update(test_data)
    return test_input


@pytest.mark.parametrize("test_data,expected_err", [
    # good
    ({"labels": {"/usr/bin/cp": "system_u:object_r:install_exec_t:s0"}}, ""),
    ({"force_autorelabel": True}, ""),
    # bad
    ({"file_contexts": 1234}, "1234 is not of type 'string'"),
    ({"labels": "xxx"}, "'xxx' is not of type 'object'"),
    ({"force_autorelabel": "foo"}, "'foo' is not of type 'boolean'"),
])
@pytest.mark.parametrize("stage_schema", ["1"], indirect=True)
def test_schema_validation_selinux(stage_schema, test_data, expected_err):
    res = stage_schema.validate(get_test_input(test_data))
    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


@pytest.mark.parametrize("stage_schema", ["1"], indirect=True)
def test_schema_validation_selinux_file_context_required(stage_schema):
    res = stage_schema.validate(get_test_input({}, implicit_file_contexts=False))
    assert res.valid is False
    expected_err = "'file_contexts' is a required property"
    testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


@patch("osbuild.util.selinux.setfiles")
def test_selinux_file_contexts(mocked_setfiles, tmp_path, stage_module):
    options = {
        "file_contexts": "etc/selinux/thing",
    }
    stage_module.main(tmp_path, options)

    assert len(mocked_setfiles.call_args_list) == 1
    assert mocked_setfiles.call_args_list == [
        call(f"{tmp_path}/etc/selinux/thing", os.fspath(tmp_path), "")
    ]


@patch("osbuild.util.selinux.setfilecon")
@patch("osbuild.util.selinux.setfiles")
def test_selinux_labels(mocked_setfiles, mocked_setfilecon, tmp_path, stage_module):
    testutil.make_fake_input_tree(tmp_path, {
        "/usr/bin/bootc": "I'm only an imposter",
    })

    options = {
        "file_contexts": "etc/selinux/thing",
        "labels": {
            "/tree/usr/bin/bootc": "system_u:object_r:install_exec_t:s0",
        }
    }
    stage_module.main(tmp_path, options)

    assert len(mocked_setfiles.call_args_list) == 1
    assert len(mocked_setfilecon.call_args_list) == 1
    assert mocked_setfilecon.call_args_list == [
        call(f"{tmp_path}/tree/usr/bin/bootc", "system_u:object_r:install_exec_t:s0"),
    ]


@patch("osbuild.util.selinux.setfiles")
def test_selinux_force_autorelabel(mocked_setfiles, tmp_path, stage_module):  # pylint: disable=unused-argument
    for enable_autorelabel in [False, True]:
        options = {
            "file_contexts": "etc/selinux/thing",
            "force_autorelabel": enable_autorelabel,
        }
        stage_module.main(tmp_path, options)

        assert (tmp_path / ".autorelabel").exists() == enable_autorelabel
