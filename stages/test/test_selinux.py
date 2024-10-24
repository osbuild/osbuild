#!/usr/bin/python3

import contextlib
import os.path
import subprocess
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
    ({"file_contexts": "path/to/file_contexts"}, ""),
    ({"file_contexts": "tree:///path/to/file_contexts"}, ""),
    ({"file_contexts": "mount://disk/path/to/file_contexts"}, ""),
    ({"file_contexts": "input://tree/path/to/file_contexts"}, ""),
    ({"targets": ["mount:///boot/efi", "tree:///boot/efi"]}, ""),
    # bad
    ({"targets": ["/boot/efi"]}, "'/boot/efi' is not valid under any of the given schemas"),
    ({"file_contexts": 1234}, "1234 is not valid under any of the given schemas"),
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
    assert args == (f"{tmp_path}/etc/selinux/thing", os.fspath(tmp_path), "")
    assert kwargs == {"exclude_paths": None}


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
@pytest.mark.skipif(not testutil.has_executable("mkfs.ext4"), reason="need mkfs.ext4")
@patch("osbuild.util.selinux.setfiles")
def test_selinux_file_contexts_mounts(mocked_setfiles, tmp_path, stage_module):
    tree = tmp_path / "tree"
    tree.mkdir()
    mounts = tmp_path / "mounts"
    mounts.mkdir()

    # Create fake EXT4 disk image
    fake_disk_path = tmp_path / "fake.img"
    with fake_disk_path.open("w") as fp:
        fp.truncate(10 * 1024 * 1024)
    subprocess.run(
        ["mkfs.ext4", os.fspath(fake_disk_path)], check=True)

    with contextlib.ExitStack() as cm:
        fake_disk_mnt = mounts / "."
        subprocess.run(["mount", fake_disk_path, fake_disk_mnt], check=True)
        cm.callback(subprocess.run, ["umount", fake_disk_mnt], check=True)

        options = {
            "file_contexts": "tree:///etc/selinux/thing",
            "targets": ["mount://root/"]
        }
        args = {
            "tree": f"{tree}",
            "options": options,
            "paths": {
                "mounts": mounts,
            },
            "mounts": {"root": {"path": fake_disk_mnt}}
        }
        stage_module.main(args)

        assert len(mocked_setfiles.call_args_list) == 1
        args, kwargs = mocked_setfiles.call_args_list[0]
        assert args == (f"{tree}/etc/selinux/thing", f"{fake_disk_mnt}", "")
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
    assert args == (f"{tmp_path}/etc/selinux/thing", os.fspath(tmp_path), "")
    assert kwargs == {"exclude_paths": [f"{tmp_path}/sysroot"]}


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
    args = {
        "tree": f"{tmp_path}",
        "options": options
    }
    stage_module.main(args)

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
        args = {
            "tree": f"{tmp_path}",
            "options": options
        }
        stage_module.main(args)

        assert (tmp_path / ".autorelabel").exists() == enable_autorelabel
        if enable_autorelabel:
            assert (tmp_path / ".autorelabel").read_text() == "-F"
