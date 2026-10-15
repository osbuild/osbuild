import errno
import json
import os
import re
import subprocess
from contextlib import ExitStack
from unittest.mock import Mock, call, patch

import pytest

from osbuild.mounts import FileSystemMountService
from osbuild.util.mnt import MountGuard, MountPermissions, mount


@pytest.mark.parametrize("permissions", list(MountPermissions))
def test_mount_guard_recursive_permissions(permissions):
    target = "/target store"
    child = target + "/overlay\\with\ttabs"
    mount_table = {"filesystems": [
        {"target": target, "vfs-options": "ro,relatime"},
        {"target": child, "vfs-options": "ro,nosuid,nodev,noexec"},
    ]}
    result = subprocess.CompletedProcess([], 0, stdout=json.dumps(mount_table))
    with patch("osbuild.util.mnt.subprocess.run", return_value=result) as run:
        with MountGuard() as mg:
            mg.mount("/source", target, permissions=permissions, recursive_permissions=True)
    assert run.call_args_list[1:] == [
        call(["findmnt", "--json", "--list", "--submounts", "--mountpoint", target,
              "--output", "TARGET,VFS-OPTIONS"],
             stdout=subprocess.PIPE, encoding="utf-8", check=True),
        call(["mount", "-o", f"relatime,remount,bind,{permissions.value}", "none", target], check=True),
        call(["mount", "-o", f"nosuid,nodev,noexec,remount,bind,{permissions.value}", "none", child], check=True),
        call(["sync", "-f", target], check=True),
        call(["umount", "--lazy", target], check=True),
    ]


def test_mount_guard_permissions_are_not_recursive_by_default():
    with patch("osbuild.util.mnt.subprocess.run", return_value=Mock(returncode=0)) as run:
        with MountGuard() as mg:
            mg.mount("/source", "/target", permissions=MountPermissions.READ_WRITE)
    assert [args[0][0] for args, _kwargs in run.call_args_list] == ["mount", "sync", "umount"]


def test_mount_guard_recursive_permissions_require_permissions():
    with patch("osbuild.util.mnt.subprocess.run") as run:
        with MountGuard() as mg:
            with pytest.raises(ValueError, match="requires explicit permissions"):
                mg.mount("/source", "/target", recursive_permissions=True)
    run.assert_not_called()


@pytest.mark.parametrize("failure", ["findmnt", "mount"])
def test_mount_guard_recursive_permissions_failure_cleanup(failure):
    def run(args, **_kwargs):
        if args[0] == "findmnt":
            if failure == "findmnt":
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"filesystems": [
                {"target": "/target", "vfs-options": "ro"},
            ]}))
        if args[0] == "mount" and "none" in args:
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0)

    with patch("osbuild.util.mnt.subprocess.run", side_effect=run) as mock_run:
        with pytest.raises(subprocess.CalledProcessError):
            with MountGuard() as mg:
                mg.mount("/source", "/target", permissions=MountPermissions.READ_WRITE, recursive_permissions=True)
    assert mock_run.call_args_list[-2:] == [
        call(["sync", "-f", "/target"], check=True),
        call(["umount", "--lazy", "/target"], check=True),
    ]


@pytest.mark.parametrize("mountpoints", [["/target-neighbour"], ["/target", "/target-neighbour"]])
def test_mount_guard_recursive_permissions_stay_in_subtree(mountpoints):
    result = subprocess.CompletedProcess([], 0, stdout=json.dumps({"filesystems": [
        {"target": path, "vfs-options": "ro"} for path in mountpoints
    ]}))
    with patch("osbuild.util.mnt.subprocess.run", return_value=result) as run:
        with pytest.raises(RuntimeError, match="Invalid mount subtree"):
            with MountGuard() as mg:
                mg.mount("/source", "/target", permissions=MountPermissions.READ_WRITE, recursive_permissions=True)
    assert len([args for args, _kwargs in run.call_args_list if args[0][0] == "mount"]) == 1


@pytest.mark.skipif(os.getuid() != 0, reason="root only; run in a private mount namespace")
def test_mount_guard_recursive_permissions_real_mounts(tmp_path):
    source, input_path, alias = [tmp_path / name for name in ("source", "input", "alias store\\with\ttabs")]
    for path in (source, input_path, alias):
        path.mkdir()
    with ExitStack() as mounts:
        subprocess.run(["mount", "-t", "tmpfs", "tmpfs", os.fspath(source)], check=True)
        mounts.callback(subprocess.run, ["umount", "--lazy", os.fspath(source)], check=True)
        child = source / "overlay"
        child.mkdir()
        (child / "underlying").touch()
        # A separate child filesystem makes a lost submount visible to the test.
        subprocess.run(["mount", "-t", "tmpfs", "-o", "nosuid,nodev,noexec", "tmpfs", os.fspath(child)], check=True)
        mounts.callback(subprocess.run, ["umount", "--lazy", os.fspath(child)], check=True)
        (child / "image").write_text("bound image data", encoding="utf-8")
        subprocess.run(["mount", "--rbind", os.fspath(source), os.fspath(input_path)], check=True)
        mounts.callback(subprocess.run, ["umount", "--lazy", os.fspath(input_path)], check=True)
        # Model the build root's read-only input, including its child mount.
        subprocess.run(["mount", "-o", "remount,bind,ro,nosuid,nodev,noexec", "none",
                        os.fspath(input_path / "overlay")], check=True)
        subprocess.run(["mount", "-o", "remount,bind,ro", "none", os.fspath(input_path)], check=True)
        # Root-only permissions leave the child read-only and reproduce EROFS.
        with MountGuard() as mg:
            mg.mount(input_path, alias, permissions=MountPermissions.READ_WRITE)
            with pytest.raises(OSError) as exc:
                (alias / "overlay" / ".has-mount-program").touch()
            assert exc.value.errno == errno.EROFS
        with MountGuard() as mg:
            mg.mount(input_path, alias, permissions=MountPermissions.READ_WRITE, recursive_permissions=True)
            assert (alias / "overlay" / "image").read_text(encoding="utf-8") == "bound image data"
            assert not (alias / "overlay" / "underlying").exists()
            (alias / "overlay" / ".has-mount-program").touch()
            flags = os.statvfs(alias / "overlay").f_flag
            for flag in (os.ST_NOSUID, os.ST_NODEV, os.ST_NOEXEC):
                assert flags & flag
            assert not flags & os.ST_RDONLY
            assert os.statvfs(input_path).f_flag & os.ST_RDONLY
            assert os.statvfs(input_path / "overlay").f_flag & os.ST_RDONLY
        assert not (alias / "overlay").exists()


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_mount_failure_msg(tmp_path):
    with pytest.raises(RuntimeError) as e:
        mount("/dev/invalid-src", tmp_path)
    # latest util-linux mount uses fsconfig(2) instead of mount(2) so the
    # error is different
    assert re.search(r"special device /dev/invalid-src does not exist|Can't lookup blockdev.", str(e.value))


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_mount_guard_failure_msg(tmp_path):
    with pytest.raises(RuntimeError) as e:
        with MountGuard() as mg:
            mg.mount("/dev/invalid-src", tmp_path)
    # latest util-linux mount uses fsconfig(2) instead of mount(2) so the
    # error is different
    assert re.search(r"special device /dev/invalid-src does not exist|Can't lookup blockdev.", str(e.value))


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_mount_guard_incorrect_permissions_msg(tmp_path):
    with pytest.raises(ValueError) as e:
        with MountGuard() as mg:
            mg.mount("/dev/invalid-src", tmp_path, permissions="abc")
    assert "unknown filesystem permissions" in str(e.value)


# This needs a proper refactor so that FileSystemMountService just uses
# a common mount helper.
class FakeFileSystemMountService(FileSystemMountService):
    def __init__(self, args=None):  # pylint: disable=super-init-not-called
        # override __init__ to make it testable
        pass

    def translate_options(self, options):
        return options


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_osbuild_mount_failure_msg(tmp_path):
    mnt_service = FakeFileSystemMountService()
    # yes, we have a third way of mounting things
    with pytest.raises(RuntimeError) as e:
        args = {
            "source": "/dev/invalid-src",
            "target": os.fspath(tmp_path),
            "root": "/",
            "options": [],
        }
        mnt_service.mount(args)
    assert re.search(
        r"special device /dev/invalid-src does not exist|Can't open blockdev.|Can't lookup blockdev", str(e.value))
