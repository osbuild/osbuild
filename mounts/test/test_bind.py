#!/usr/bin/python3

import os
import pathlib
from unittest.mock import patch

import pytest

import osbuild.meta
from osbuild import testutil

MOUNTS_NAME = "org.osbuild.bind"


@patch("subprocess.run")
def test_bind_mount_simple(mocked_run, mounts_service):
    fake_tree_path = "/tmp/osbuild/.osbuild/tmp/buildroot-tmp-_ym0rt5a/mounts/"
    fake_mountroot_path = "/tmp/osbuild/.osbuild/stage/uuid-e7443c948dff406d88bcbb7658a31f0f/data/tree/"

    fake_args = {
        "tree": fake_tree_path,
        "root": fake_mountroot_path,
        "target": "tree://",
        "options": {
            "source": "mount://",
        }
    }
    mounts_service.mount(fake_args)
    assert len(mocked_run.call_args_list) == 1
    args, kwargs = mocked_run.call_args_list[0]
    assert args[0] == ["mount", "--rbind", fake_mountroot_path, fake_tree_path]
    assert kwargs == {"check": True}


@patch("subprocess.run")
def test_bind_umount_simple(mocked_run, mounts_service):
    # nothing mounted yet, nothing is done
    mounts_service.umount()
    assert len(mocked_run.call_args_list) == 0
    # pretend a mount
    mounts_service.mountpoint = "/something"
    mounts_service.umount()
    assert len(mocked_run.call_args_list) == 1
    args, kwargs = mocked_run.call_args_list[0]
    assert args[0] == ["umount", "-R", "-v", "/something"]
    assert kwargs == {"check": True}
    # mountpoint is cleared
    assert mounts_service.mountpoint == ""
    # ensure we do not umount twice
    mounts_service.umount()
    assert len(mocked_run.call_args_list) == 1


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({}, "'name' is a required property"),
    ({}, "'target' is a required property"),
    ({}, "'source' is a required property"),
    # good
    ({"name": "bind", "target": "tree://", "options": {"source": "mount://"}}, ""),
])
def test_parameters_validation(test_data, expected_err):
    root = pathlib.Path(__file__).parent.parent.parent
    mod_info = osbuild.meta.ModuleInfo.load(root, "Mount", MOUNTS_NAME)
    schema = osbuild.meta.Schema(mod_info.get_schema(), MOUNTS_NAME)
    test_input = {
        "type": MOUNTS_NAME,
        "options": {}
    }
    test_input.update(test_data)
    res = schema.validate(test_input)
    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err)


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
def test_bind_mount_integration(tmp_path, mounts_service):
    fake_tree_path = tmp_path / "mounts"
    fake_tree_path.mkdir(parents=True, exist_ok=True)

    fake_mountroot_path = tmp_path / "uuid-1234/data/tree"
    fake_mountroot_path.mkdir(parents=True, exist_ok=True)
    (fake_mountroot_path / "in-src-mnt").write_text("", encoding="utf8")

    fake_args = {
        "tree": fake_tree_path,
        "root": fake_mountroot_path,
        "target": "tree://",
        "options": {
            "source": "mount://",
        }
    }
    assert not (fake_tree_path / "in-src-mnt").exists()
    mounts_service.mount(fake_args)
    assert (fake_tree_path / "in-src-mnt").exists()
    mounts_service.umount()
    assert not (fake_tree_path / "in-src-mnt").exists()
