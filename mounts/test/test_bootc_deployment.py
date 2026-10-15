#!/usr/bin/python3

import os
import pathlib
import subprocess
from unittest.mock import patch

import pytest

import osbuild.meta
from osbuild import testutil

MOUNTS_NAME = "org.osbuild.bootc.deployment"

STAGING = "/run/osbuild-bootc-deployment"


@pytest.fixture(name="fake_buildroot")
def fake_buildroot_fixture(tmp_path):
    buildroot = tmp_path / "buildroot"
    for d in ["proc", "dev", "sys", "run", "tmp"]:
        (buildroot / d).mkdir(parents=True)
    return buildroot


def _fake_args(tmp_path, buildroot, source=None):
    args = {
        "tree": os.fspath(tmp_path / "tree"),
        "root": os.fspath(tmp_path / "mounts"),
        "buildroot": os.fspath(buildroot) if buildroot else None,
        "options": {},
    }
    if source:
        args["options"]["source"] = source
    return args


def _run_calls(mocked_run, root):
    """The commands run, without those of the Chroot helper that only set up /proc, /dev and /sys"""
    chroot_mounts = {os.path.join(root, d) for d in ["proc", "dev", "sys"]}
    return [c[0][0] for c in mocked_run.call_args_list
            if c[0][0][-1] not in chroot_mounts]


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({"options": {"source": "other"}}, "'other' does not match '^(mount|tree)$'"),
    ({"options": {"deployment": {"default": True}}}, "Additional properties are not allowed"),
    ({"options": {}, "target": "/"}, "Additional properties are not allowed"),
    # good
    ({}, ""),
    ({"options": {"source": "mount"}}, ""),
    ({"options": {"source": "tree"}}, ""),
])
def test_parameters_validation(test_data, expected_err):
    root = pathlib.Path(__file__).parent.parent.parent
    mod_info = osbuild.meta.ModuleInfo.load(root, "Mount", MOUNTS_NAME)
    schema = osbuild.meta.Schema(mod_info.get_schema(), MOUNTS_NAME)
    test_input = {
        "name": "bootc.deployment",
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


def _bootc_cmd(root):
    return ["unshare", "--net", "--pid", "--fork", "--kill-child", "chroot", root,
            "bootc", "install", "mount",
            "--sysroot", f"{STAGING}/sysroot", "--latest", f"{STAGING}/deployment"]


def _fake_run(failing=()):
    """A subprocess.run replacement: commands whose start is in `failing` fail
    (raising with check=True), "mountpoint" says it is none, everything else works"""
    def fake_run(cmd, **kwargs):
        if any(cmd[:len(f)] == f for f in failing):
            if kwargs.get("check"):
                raise subprocess.CalledProcessError(1, cmd)
            return subprocess.CompletedProcess(cmd, 1)
        return subprocess.CompletedProcess(cmd, 32 if cmd[0] == "mountpoint" else 0)
    return fake_run


@pytest.mark.parametrize("source,target_key", [
    (None, "tree"),
    ("tree", "tree"),
    ("mount", "root"),
])
@patch("os.makedirs")
@patch("subprocess.run")
def test_bootc_deployment_mount(mocked_run, _mocked_makedirs, tmp_path, fake_buildroot, mounts_service,
                                source, target_key):
    mocked_run.side_effect = _fake_run()
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    args = _fake_args(tmp_path, fake_buildroot, source)
    target = args[target_key]
    root = os.fspath(tmpdir / "root")
    staging = root + STAGING

    with patch("tempfile.mkdtemp", return_value=os.fspath(tmpdir)):
        mounts_service.mount(args)

    assert _run_calls(mocked_run, root) == [
        ["mount", "--bind", "-o", "ro", "--make-private", os.fspath(fake_buildroot), root],
        ["mount", "-t", "tmpfs", "--make-private", "tmpfs", f"{root}/run"],
        ["mount", "-t", "tmpfs", "--make-private", "tmpfs", f"{root}/tmp"],
        # recursively, and before the bind mount that hides them, so that
        # bootc sees a separate /boot and ESP (ostree needs /boot)
        ["mount", "--rbind", "--make-rprivate", target, f"{staging}/sysroot"],
        ["mount", "--bind", "--make-private", target, target],
        _bootc_cmd(root),
        ["mount", "--move", f"{staging}/deployment", target],
    ]
    assert mounts_service.mountpoint == target
    # the staging area stays until the deployment is unmounted
    assert tmpdir.exists()

    mocked_run.reset_mock()
    mounts_service.umount()
    assert _run_calls(mocked_run, root) == [
        ["sync", "-f", target],
        ["umount", "-v", "-R", target],
        ["mountpoint", "-q", target],
        # not lazily
        ["umount", "-R", root],
    ]
    assert not tmpdir.exists()
    assert mounts_service.mountpoint is None

    # nothing is unmounted twice
    mocked_run.reset_mock()
    mounts_service.umount()
    mocked_run.assert_not_called()


@patch("os.makedirs")
@patch("subprocess.run")
def test_bootc_deployment_umount_staging_busy(mocked_run, _mocked_makedirs, tmp_path, fake_buildroot,
                                              mounts_service):
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    root = os.fspath(tmpdir / "root")
    mocked_run.side_effect = _fake_run(failing=[["umount", "-R", root]])
    with patch("tempfile.mkdtemp", return_value=os.fspath(tmpdir)):
        mounts_service.mount(_fake_args(tmp_path, fake_buildroot))

    # something still using the physical root fails the unmount
    with pytest.raises(subprocess.CalledProcessError):
        mounts_service.umount()
    assert tmpdir.exists()


@pytest.mark.parametrize("cleanup_fails", [False, True])
@patch("os.makedirs")
@patch("subprocess.run")
def test_bootc_deployment_mount_bootc_fails(mocked_run, _mocked_makedirs, tmp_path, fake_buildroot, mounts_service,
                                            cleanup_fails):
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    args = _fake_args(tmp_path, fake_buildroot)
    target = args["tree"]
    root = os.fspath(tmpdir / "root")
    failing = [["unshare"]]
    if cleanup_fails:
        failing += [["umount", "-R", root], ["umount", target]]
    mocked_run.side_effect = _fake_run(failing)

    with patch("tempfile.mkdtemp", return_value=os.fspath(tmpdir)):
        # bootc's error, even if cleaning up fails too
        with pytest.raises(subprocess.CalledProcessError) as e:
            mounts_service.mount(args)
    assert e.value.cmd == _bootc_cmd(root)

    calls = _run_calls(mocked_run, root)
    # the deployment is not moved, and everything mounted so far is
    # unmounted again: the staging area and the private mount of the target
    assert calls[-3:] == [
        _bootc_cmd(root),
        ["umount", "-R", root],
        ["umount", target],
    ]
    assert tmpdir.exists() == cleanup_fails
    assert mounts_service.mountpoint is None
    if not cleanup_fails:
        # nothing to clean up on stop
        mocked_run.reset_mock()
        mounts_service.umount()
        mocked_run.assert_not_called()


@patch("os.makedirs")
@patch("subprocess.run")
def test_bootc_deployment_mount_staging_fails(mocked_run, _mocked_makedirs, tmp_path, fake_buildroot, mounts_service):
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    args = _fake_args(tmp_path, fake_buildroot)
    target = args["tree"]
    root = os.fspath(tmpdir / "root")
    mocked_run.side_effect = _fake_run(failing=[["mount", "--rbind"]])

    with patch("tempfile.mkdtemp", return_value=os.fspath(tmpdir)):
        with pytest.raises(subprocess.CalledProcessError):
            mounts_service.mount(args)

    calls = _run_calls(mocked_run, root)
    # the target was not bind mounted yet, so it is left alone
    assert calls[-2:] == [
        ["mount", "--rbind", "--make-rprivate", target, root + STAGING + "/sysroot"],
        ["umount", "-R", root],
    ]
    assert ["umount", target] not in calls
    assert not tmpdir.exists()


@pytest.mark.parametrize("missing,expected_err", [
    (None, "no build root"),
    (["proc"], "build root has no /proc: "),
    (["dev", "tmp"], "build root has no /dev, /tmp: "),
])
@patch("subprocess.run")
def test_bootc_deployment_mount_bad_buildroot(mocked_run, tmp_path, fake_buildroot, mounts_service,
                                              missing, expected_err):
    buildroot = None
    if missing is not None:
        buildroot = fake_buildroot
        for d in missing:
            (buildroot / d).rmdir()

    with pytest.raises(RuntimeError, match=expected_err):
        mounts_service.mount(_fake_args(tmp_path, buildroot))
    # checked before anything is mounted
    mocked_run.assert_not_called()


@patch("subprocess.run")
def test_bootc_deployment_umount_leftover(mocked_run, mounts_service):
    # util-linux before 2.39 can leave the moved mount behind after umount -R
    returncodes = iter([0, 0, 0, 0, 32])
    mocked_run.side_effect = lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, next(returncodes))
    mounts_service.mountpoint = "/something"
    mounts_service.check = True
    mounts_service.umount()
    assert [c[0][0] for c in mocked_run.call_args_list] == [
        ["sync", "-f", "/something"],
        ["umount", "-v", "-R", "/something"],
        ["mountpoint", "-q", "/something"],
        ["umount", "-v", "/something"],
        ["mountpoint", "-q", "/something"],
    ]
