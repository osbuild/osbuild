#!/usr/bin/python3

import os.path
from unittest.mock import call, patch

import pytest  # type: ignore

from osbuild import testutil

STAGE_NAME = "org.osbuild.selinux"


def get_test_input(test_data, file_contexts=False, labels=False):
    test_input = {
        "type": STAGE_NAME,
        "options": {}
    }
    if file_contexts:
        test_input["options"]["file_contexts"] = "some-context"
    if labels:
        test_input["options"]["labels"] = {"/path/to/file": "label_to_apply"}

    test_input["options"].update(test_data)
    return test_input


@pytest.mark.parametrize("test_data,expected_err", [
    # good
    ({"labels": {"/usr/bin/cp": "system_u:object_r:install_exec_t:s0"}}, ""),
    ({"force_autorelabel": True}, ""),
    ({"exclude_paths": ["/sysroot"]}, ""),
    ({"target": "mount://disk/boot/efi"}, ""),
    ({"target": "tree:///boot/efi"}, ""),
    # bad
    ({"target": "/boot/efi"}, "'/boot/efi' does not match '^mount://[^/]+/|^tree:///'"),
    ({"file_contexts": 1234}, "1234 is not of type 'string'"),
    ({"labels": "xxx"}, "'xxx' is not of type 'object'"),
    ({"force_autorelabel": "foo"}, "'foo' is not of type 'boolean'"),
])
def test_schema_validation_selinux(stage_schema, test_data, expected_err):
    res = stage_schema.validate(get_test_input(test_data, file_contexts=True, labels=False))
    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


def test_schema_validation_selinux_required_options(stage_schema):
    res = stage_schema.validate(get_test_input({}, file_contexts=False, labels=False))
    assert res.valid is False
    expected_err = "{} is not valid under any of the given schemas"
    testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)
    res = stage_schema.validate(get_test_input({}, file_contexts=True, labels=False))
    assert res.valid is True
    res = stage_schema.validate(get_test_input({}, file_contexts=False, labels=True))
    assert res.valid is True


@patch("osbuild.util.selinux.setfiles")
def test_selinux_file_contexts(mocked_setfiles, tmp_path, stage_module):
    options = {
        "file_contexts": "etc/selinux/thing",
    }
    args = {
        "tree": f"{tmp_path}",
        "options": options
    }
    stage_module.main(args)

    assert len(mocked_setfiles.call_args_list) == 1
    args, kwargs = mocked_setfiles.call_args_list[0]
    assert args == (f"{tmp_path}/etc/selinux/thing", os.fspath(tmp_path), "/")
    assert kwargs == {"exclude_paths": None}


@patch("osbuild.util.selinux.setfiles")
def test_selinux_file_contexts_mounts(mocked_setfiles, tmp_path, stage_module):
    tree = tmp_path / "tree"
    mounts = tmp_path / "mounts"

    args = {
        "tree": f"{tree}",
        "options": {
            "file_contexts": "etc/selinux/thing",
            "target": "mount://root/"
        },
        "paths": {
            "mounts": mounts,
        },
        "mounts": {
            "root": {"path": mounts}
        }
    }
    stage_module.main(args)

    assert len(mocked_setfiles.call_args_list) == 1
    args, kwargs = mocked_setfiles.call_args_list[0]
    assert args == (f"{tree}/etc/selinux/thing", f"{mounts}", "/")
    assert kwargs == {"exclude_paths": None}


@patch("osbuild.util.selinux.setfiles")
def test_selinux_file_contexts_exclude(mocked_setfiles, tmp_path, stage_module):
    options = {
        "file_contexts": "etc/selinux/thing",
        "exclude_paths": ["/sysroot"],
    }
    args = {
        "tree": f"{tmp_path}",
        "options": options
    }
    stage_module.main(args)

    assert len(mocked_setfiles.call_args_list) == 1
    args, kwargs = mocked_setfiles.call_args_list[0]
    assert args == (f"{tmp_path}/etc/selinux/thing", os.fspath(tmp_path), "/")
    assert kwargs == {"exclude_paths": [f"{tmp_path}/sysroot"]}


@patch("osbuild.util.selinux.setfilecon")
@patch("osbuild.util.selinux.setfiles")
def test_selinux_labels(mocked_setfiles, mocked_setfilecon, tmp_path, stage_module):
    tree = tmp_path / "tree"
    testutil.make_fake_input_tree(tmp_path, {
        "/usr/bin/echo": "I'm only an imposter",
        "/sbin/sulogin": "I'm only an imposter",
    })

    options = {
        "file_contexts": "etc/selinux/thing",
        "labels": {
            "tree:///usr/bin/echo": "system_u:object_r:bin_t:s0",
            "/sbin/sulogin": "system_u:object_r:sulogin_exec_t:s0",
        }
    }
    args = {
        "tree": tree,
        "options": options
    }
    stage_module.main(args)

    assert len(mocked_setfiles.call_args_list) == 1
    assert len(mocked_setfilecon.call_args_list) == 2
    assert mocked_setfilecon.call_args_list == [
        call(f"{tree}/usr/bin/echo", "system_u:object_r:bin_t:s0"),
        call(f"{tree}/sbin/sulogin", "system_u:object_r:sulogin_exec_t:s0"),
    ]


@patch("osbuild.util.selinux.setfilecon")
def test_selinux_labels_mount(mocked_setfilecon, tmp_path, stage_module):
    tree = tmp_path / "tree"
    mounts = tmp_path / "mounts"

    testutil.make_fake_tree(mounts, {"/sbin/su": "I'm only an imposter"})
    args = {
        "tree": tree,
        "options": {
            "labels": {
                "mount://root/sbin/su": "system_u:object_r:su_exec_t:s0",
            }
        },
        "paths": {
            "mounts": mounts,
        },
        "mounts": {
            "root": {"path": mounts}
        }
    }
    stage_module.main(args)

    assert len(mocked_setfilecon.call_args_list) == 1
    assert mocked_setfilecon.call_args_list == [
        call(f"{mounts}/sbin/su", "system_u:object_r:su_exec_t:s0"),
    ]


@patch("osbuild.util.selinux.setfiles")
def test_selinux_force_autorelabel(mocked_setfiles, tmp_path, stage_module):  # pylint: disable=unused-argument
    for enable_autorelabel in [False, True]:
        options = {
            "file_contexts": "etc/selinux/thing",
            "force_autorelabel": enable_autorelabel,
        }
        args = {
            "tree": f"{tmp_path}",
            "options": options
        }
        stage_module.main(args)

        assert (tmp_path / ".autorelabel").exists() == enable_autorelabel
        if enable_autorelabel:
            assert (tmp_path / ".autorelabel").read_text() == "-F"
