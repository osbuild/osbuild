#
# Tests for the 'osbuild.util.fscache' module.
#

# pylint: disable=protected-access

import contextlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

import pytest

from osbuild.util import fscache


@pytest.fixture(name="tmpdir")
def tmpdir_fixture():
    with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
        yield tmp


def sleep_for_fs():
    """Sleep a tiny amount of time for atime/mtime updates to show up in fs"""
    time.sleep(0.05)


def has_precise_fs_timestamps():
    with tempfile.TemporaryDirectory(dir="/var/tmp") as tmpdir:
        stamp_path = pathlib.Path(tmpdir) / "stamp"
        stamp_path.write_bytes(b"m1")
        mtime1 = stamp_path.stat().st_mtime
        sleep_for_fs()
        stamp_path.write_bytes(b"m2")
        mtime2 = stamp_path.stat().st_mtime
        return mtime2 > mtime1


def test_calculate_space(tmpdir):
    #
    # Test the `_calculate_space()` helper and verify it only includes file
    # content in its calculation.
    #
    def du(path_target):
        env = os.environ.copy()
        env["POSIXLY_CORRECT"] = "1"
        output = subprocess.check_output(["du", "-s", path_target], env=env, encoding="utf8")
        return int(output.split()[0].strip()) * 512

    test_dir = os.path.join(tmpdir, "dir")
    os.mkdir(test_dir)
    assert fscache.FsCache._calculate_space(test_dir) == du(test_dir)

    with open(os.path.join(tmpdir, "dir", "file"), "x", encoding="utf8") as f:
        pass
    assert fscache.FsCache._calculate_space(test_dir) == du(test_dir)

    with open(os.path.join(tmpdir, "dir", "file"), "w", encoding="utf8") as f:
        f.write("foobar")
    assert fscache.FsCache._calculate_space(test_dir) == du(test_dir)

    os.makedirs(os.path.join(test_dir, "dir"))
    assert fscache.FsCache._calculate_space(test_dir) == du(test_dir)

    with open(os.path.join(test_dir, "sparse-file"), "wb") as f:
        f.truncate(10 * 1024 * 1024)
        f.write(b"I'm not an empty file")
    assert fscache.FsCache._calculate_space(test_dir) == du(test_dir)


def test_pathlike(tmpdir):
    #
    # Verify behavior of `__fspath__()`.
    #

    class Wrapper:
        def __init__(self, path: str):
            self._path = path

        def __fspath__(self) -> str:
            return self._path

    # Test with a plain string as argument
    dir_str: str = os.fspath(tmpdir)
    cache1 = fscache.FsCache("osbuild-test-appid", dir_str)
    assert os.fspath(cache1) == tmpdir
    assert os.path.join(cache1, "foobar") == os.path.join(tmpdir, "foobar")

    # Test with a wrapper-type as argument
    dir_pathlike: Wrapper = Wrapper(os.fspath(tmpdir))
    cache2 = fscache.FsCache("osbuild-test-appid", dir_pathlike)
    assert os.fspath(cache2) == tmpdir
    assert os.path.join(cache2, "foobar") == os.path.join(tmpdir, "foobar")


def test_path(tmpdir):
    #
    # Verify behavior of `_path()`.
    #

    cache = fscache.FsCache("osbuild-test-appid", tmpdir)
    with cache:
        assert cache._path() == cache._path_cache
        assert cache._path("dir") == os.path.join(cache._path_cache, "dir")
        assert cache._path("dir", "file") == os.path.join(cache._path_cache, "dir", "file")


def test_atomic_open(tmpdir):
    #
    # Verify the `_atomic_open()` helper correctly opens existing files and
    # takes a lock.
    #

    cache = fscache.FsCache("osbuild-test-appid", tmpdir)
    with cache:
        # Must never create files.
        with pytest.raises(OSError):
            with cache._atomic_open("file", write=False, wait=False) as f:
                pass

        # Create the file with "foo" as content.
        with open(os.path.join(tmpdir, "file"), "x", encoding="utf8") as f:
            f.write("foo")

        # Open and acquire a write-lock. Then verify a read-lock fails.
        with cache._atomic_open("file", write=True, wait=False):
            with pytest.raises(BlockingIOError):
                with cache._atomic_open("file", write=False, wait=False):
                    pass


def test_atomic_file(tmpdir):
    #
    # Verify behavior of `_atomic_file()` as replacement for `O_TMPFILE`.
    #

    cache = fscache.FsCache("osbuild-test-appid", tmpdir)
    with cache:
        rpath_store = cache._dirname_objects
        path_store = os.path.join(cache._path_cache, rpath_store)

        # Initially the store is empty.
        assert len(list(os.scandir(path_store))) == 0

        # Create a file and verify there is almost exactly 1 file in the store.
        with cache._atomic_file(os.path.join(rpath_store, "file"), rpath_store) as f:
            assert len(list(os.scandir(path_store))) == 1
            f.write("foo")
        assert len(list(os.scandir(path_store))) == 1

        # Verify `ignore_exist=False` works as expected.
        with pytest.raises(OSError):
            with cache._atomic_file(os.path.join(rpath_store, "file"), rpath_store) as f:
                # Temporarily, there will be 2 files.
                assert len(list(os.scandir(path_store))) == 2
                f.write("bar")
        assert len(list(os.scandir(path_store))) == 1
        with open(os.path.join(path_store, "file"), "r", encoding="utf8") as f:
            assert f.read() == "foo"

        # Verify `ignore_exist=True` works as expected.
        with cache._atomic_file(os.path.join(rpath_store, "file"), rpath_store, ignore_exist=True) as f:
            f.write("bar")
        assert len(list(os.scandir(path_store))) == 1
        with open(os.path.join(path_store, "file"), "r", encoding="utf8") as f:
            assert f.read() == "foo"

        # Verify `replace=True`.
        with cache._atomic_file(os.path.join(rpath_store, "file"), rpath_store, replace=True) as f:
            f.write("bar")
        assert len(list(os.scandir(path_store))) == 1
        with open(os.path.join(path_store, "file"), "r", encoding="utf8") as f:
            assert f.read() == "bar"

        # Combining `replace` and `ignore_exist` is not allowed.
        with pytest.raises(AssertionError):
            with cache._atomic_file(
                    os.path.join(rpath_store, "file"),
                    rpath_store,
                    replace=True,
                    ignore_exist=True,
            ) as f:
                pass


def test_atomic_dir(tmpdir):
    #
    # Verify the `_atomic_dir()` helper correctly creates anonymous files
    # and yields the name and lock-file.
    #

    cache = fscache.FsCache("osbuild-test-appid", tmpdir)
    with cache:
        # The relative-path must exist, so expect an error if it does not.
        with pytest.raises(OSError):
            cache._atomic_dir("dir")

        assert len(list(os.scandir(os.path.join(tmpdir, cache._dirname_objects)))) == 0

        (name, lockfd) = cache._atomic_dir(cache._dirname_objects)
        assert name.startswith("uuid-")
        assert len(name) == 37
        assert lockfd >= 0
        os.close(lockfd)

        assert len(list(os.scandir(os.path.join(tmpdir, cache._dirname_objects)))) == 1


def test_scaffolding(tmpdir):
    #
    # Verify that the cache creates scaffolding when entered.
    #

    cache = fscache.FsCache("osbuild-test-appid", tmpdir)

    assert len(list(os.scandir(tmpdir))) == 0

    with cache:
        pass

    assert len(list(os.scandir(tmpdir))) == 6
    assert len(list(os.scandir(os.path.join(tmpdir, cache._dirname_objects)))) == 0
    assert len(list(os.scandir(os.path.join(tmpdir, cache._dirname_stage)))) == 0

    with open(os.path.join(tmpdir, cache._filename_cache_tag), "r", encoding="utf8") as f:
        assert len(f.read()) > 0
    with open(os.path.join(tmpdir, cache._filename_cache_info), "r", encoding="utf8") as f:
        assert json.load(f) == {"version": 1}
    with open(os.path.join(tmpdir, cache._filename_cache_lock), "r", encoding="utf8") as f:
        assert f.read() == ""
    with open(os.path.join(tmpdir, cache._filename_cache_size), "r", encoding="utf8") as f:
        assert f.read() == "0"


def test_cachedir_tag(tmpdir):
    #
    # Verify compatibility to the cachedir-tag specification.
    #

    cache = fscache.FsCache("osbuild-test-appid", tmpdir)

    with cache:
        pass

    with open(os.path.join(tmpdir, "CACHEDIR.TAG"), "r", encoding="utf8") as f:
        assert f.read(43) == "Signature: 8a477f597d28d172789f06886806bc55"


def test_cache_info(tmpdir):
    #
    # Verify that the cache reads and augments cache information. Also verify
    # the default values.
    #

    cache = fscache.FsCache("osbuild-test-appid", tmpdir)

    with cache:
        assert cache._info == fscache.FsCacheInfo(version=1)
        assert cache.info == cache._info

        assert cache.info.maximum_size is None
        assert cache.info.creation_boot_id is None
        cache.info = fscache.FsCacheInfo(maximum_size=1024)
        assert cache.info.maximum_size == 1024
        assert cache.info.creation_boot_id is None
        cache.info = fscache.FsCacheInfo(creation_boot_id="0" * 32)
        assert cache.info.maximum_size == 1024
        assert cache.info.creation_boot_id == "0" * 32
        cache.info = fscache.FsCacheInfo(maximum_size=2048, creation_boot_id="1" * 32)
        assert cache.info.maximum_size == 2048
        assert cache.info.creation_boot_id == "1" * 32

    assert not fscache.FsCacheInfo().to_json()
    assert fscache.FsCacheInfo(creation_boot_id="0" * 32).to_json() == {
        "creation-boot-id": "0" * 32,
    }
    assert fscache.FsCacheInfo(creation_boot_id="0" * 32, maximum_size=1024).to_json() == {
        "creation-boot-id": "0" * 32,
        "maximum-size": 1024,
    }

    assert fscache.FsCacheInfo.from_json({}) == fscache.FsCacheInfo()
    assert fscache.FsCacheInfo.from_json(None) == fscache.FsCacheInfo()
    assert fscache.FsCacheInfo.from_json("foobar") == fscache.FsCacheInfo()
    assert fscache.FsCacheInfo.from_json({
        "creation-boot-id": "0" * 32,
    }) == fscache.FsCacheInfo(creation_boot_id="0" * 32)
    assert fscache.FsCacheInfo.from_json({
        "creation-boot-id": "0" * 32,
        "maximum-size": 1024,
    }) == fscache.FsCacheInfo(creation_boot_id="0" * 32, maximum_size=1024)
    assert fscache.FsCacheInfo.from_json({
        "creation-boot-id": "0" * 32,
        "maximum-size": 1024,
    }) == fscache.FsCacheInfo(creation_boot_id="0" * 32, maximum_size=1024)
    assert fscache.FsCacheInfo.from_json({
        "creation-boot-id": "0" * 32,
        "unknown0": "foobar",
        "unknown1": ["foo", "bar"],
    }) == fscache.FsCacheInfo(creation_boot_id="0" * 32)


def test_store(tmpdir):
    #
    # API tests for the `store()` method.
    #

    cache = fscache.FsCache("osbuild-test-appid", tmpdir)

    with pytest.raises(AssertionError):
        with cache.store("foobar"):
            pass

    with cache:
        with pytest.raises(ValueError):
            with cache.store(""):
                pass


def test_load(tmpdir):
    #
    # API tests for the `load()` method.
    #

    cache = fscache.FsCache("osbuild-test-appid", tmpdir)

    with pytest.raises(AssertionError):
        with cache.load("foobar"):
            pass

    with cache:
        with pytest.raises(ValueError):
            with cache.load(""):
                pass


def test_store_tree(tmpdir):
    #
    # API tests for the `store_tree()` method.
    #

    cache = fscache.FsCache("osbuild-test-appid", tmpdir)

    with pytest.raises(AssertionError):
        cache.store_tree("foobar", "invalid/dir")

    with cache:
        cache.info = cache.info._replace(maximum_size=1024 * 1024 * 1024)

        with pytest.raises(ValueError):
            cache.store_tree("", "invalid/dir")
        with pytest.raises(RuntimeError):
            cache.store_tree("key", "invalid/dir")

        with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
            with open(os.path.join(tmp, "outside"), "x", encoding="utf8") as f:
                f.write("foo")
            os.mkdir(os.path.join(tmp, "tree"))
            with open(os.path.join(tmp, "tree", "inside"), "x", encoding="utf8") as f:
                f.write("bar")
            with open(os.path.join(tmp, "tree", "more-inside"), "x", encoding="utf8") as f:
                f.write("foobar")

            cache.store_tree("key", os.path.join(tmp, "tree"))

            with cache.load("key") as rpath:
                assert len(list(os.scandir(os.path.join(cache, rpath)))) == 1
                assert len(list(os.scandir(os.path.join(cache, rpath, "tree")))) == 2
                with open(os.path.join(cache, rpath, "tree", "inside"), "r", encoding="utf8") as f:
                    assert f.read() == "bar"
                with open(os.path.join(cache, rpath, "tree", "more-inside"), "r", encoding="utf8") as f:
                    assert f.read() == "foobar"


def test_basic(tmpdir):
    #
    # A basic cache store+load test.
    #

    cache = fscache.FsCache("osbuild-test-appid", tmpdir)
    with cache:
        cache.info = cache.info._replace(maximum_size=1024 * 1024)

        with cache.stage() as rpath:
            with open(os.path.join(tmpdir, rpath, "bar"), "x", encoding="utf8") as f:
                f.write("foobar")

        with pytest.raises(fscache.FsCache.MissError):
            with cache.load("foo") as rpath:
                pass

        with cache.store("foo") as rpath:
            with open(os.path.join(tmpdir, rpath, "bar"), "x", encoding="utf8") as f:
                f.write("foobar")

        with cache.load("foo") as rpath:
            with open(os.path.join(tmpdir, rpath, "bar"), "r", encoding="utf8") as f:
                assert f.read() == "foobar"


def test_size_discard(tmpdir):
    #
    # Verify that a cache with no maximum-size configured can never store any
    # entries, but discards them immediately.
    #

    cache = fscache.FsCache("osbuild-test-appid", tmpdir)
    with cache:
        with cache.store("foo") as rpath:
            with open(os.path.join(tmpdir, rpath, "bar"), "x", encoding="utf8") as f:
                f.write("foobar")

        with pytest.raises(fscache.FsCache.MissError):
            with cache.load("foo") as rpath:
                pass


def test_cache_last_used_noent(tmpdir):
    cache = fscache.FsCache("osbuild-test-appid", tmpdir)
    with pytest.raises(fscache.FsCache.MissError):
        cache._last_used("non-existant-entry")


@pytest.mark.skipif(not has_precise_fs_timestamps(), reason="need precise fs timestamps")
def test_cache_load_updates_last_used(tmpdir):
    cache = fscache.FsCache("osbuild-test-appid", tmpdir)
    with cache:
        cache.info = cache.info._replace(maximum_size=1024 * 1024)
        with cache.store("foo"):
            pass
        with cache.load("foo"):
            pass
        load_time1 = cache._last_used("foo")
        # would be nice to have a helper for this in cache
        obj_lock_path = os.path.join(
            cache._dirname_objects, "foo", cache._filename_object_lock)
        mtime1 = os.stat(cache._path(obj_lock_path)).st_mtime
        assert load_time1 > 0
        sleep_for_fs()
        with cache.load("foo"):
            pass
        # load time is updated
        load_time2 = cache._last_used("foo")
        assert load_time2 > load_time1
        # mtime is unchanged
        mtime2 = os.stat(cache._path(obj_lock_path)).st_mtime
        assert mtime1 == mtime2


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
def test_cache_load_updates_last_used_on_noatime(tmp_path):
    mnt_path = tmp_path / "mnt"
    mnt_path.mkdir()
    with contextlib.ExitStack() as cm:
        subprocess.check_call(
            ["mount", "-t", "tmpfs", "-o", "noatime", "none", os.fspath(mnt_path)],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        cm.callback(subprocess.check_call, ["umount", os.fspath(mnt_path)], stdout=sys.stdout, stderr=sys.stderr)
        test_cache_load_updates_last_used(mnt_path)


def test_cache_full_behavior(tmp_path):
    cache = fscache.FsCache("osbuild-cache-evict", tmp_path)
    with cache:
        # use big sizes to mask the effect of dirs using 4k of space too
        cache.info = cache.info._replace(maximum_size=192 * 1024)
        # add one object to the store, we are below the limit
        with cache.store("o1") as rpath:
            rpath_f1 = os.path.join(tmp_path, rpath, "f1")
            with open(rpath_f1, "wb") as fp:
                fp.write(b'a' * 64 * 1024)
        assert cache._calculate_space(tmp_path) > 64 * 1024
        assert cache._calculate_space(tmp_path) < 128 * 1024
        with cache.load("o1") as o:
            assert o != ""
        # and one more
        with cache.store("o2") as rpath:
            rpath_f2 = os.path.join(tmp_path, rpath, "f2")
            with open(rpath_f2, "wb") as fp:
                fp.write(b'b' * 64 * 1024)
        assert cache._calculate_space(tmp_path) > 128 * 1024
        assert cache._calculate_space(tmp_path) < 192 * 1024
        with cache.load("o2") as o:
            assert o != ""
        # adding a third one will (silently) fail because the cache is full
        with cache.store("o3") as rpath:
            rpath_f3 = os.path.join(tmp_path, rpath, "f3")
            with open(rpath_f3, "wb") as fp:
                fp.write(b'b' * 128 * 1024)
        assert cache._calculate_space(tmp_path) > 128 * 1024
        assert cache._calculate_space(tmp_path) < 192 * 1024
        with pytest.raises(fscache.FsCache.MissError):
            with cache.load("o3") as o:
                pass


@pytest.mark.skipif(not has_precise_fs_timestamps(), reason="need precise fs timestamps")
def test_cache_last_used_objs(tmpdir):
    cache = fscache.FsCache("osbuild-cache-id", tmpdir)
    with cache:
        # use big sizes to mask the effect of dirs using 4k of space too
        cache.info = cache.info._replace(maximum_size=256 * 1024)
        # add objs to the store
        for obj in ["o3", "o2", "o1"]:
            with cache.store(obj):
                pass
            with cache.load(obj):
                pass
            sleep_for_fs()
        sorted_objs = cache._last_used_objs()
        assert [e[0] for e in sorted_objs] == ["o3", "o2", "o1"]
        # access o2
        with cache.load("o2"):
            pass
        sorted_objs = cache._last_used_objs()
        assert [e[0] for e in sorted_objs] == ["o3", "o1", "o2"]


@pytest.mark.skipif(not has_precise_fs_timestamps(), reason="need precise fs timestamps")
def test_cache_remove_lru(tmpdir):
    cache = fscache.FsCache("osbuild-cache-id", tmpdir)
    with cache:
        cache.info = cache.info._replace(maximum_size=-1)
        # add objs to the store
        for obj in ["o3", "o2", "o1"]:
            with cache.store(obj):
                pass
            with cache.load(obj):
                pass
            sleep_for_fs()
        # precondition check: we have least used o3,o2,o1
        sorted_objs = cache._last_used_objs()
        assert [e[0] for e in sorted_objs] == ["o3", "o2", "o1"]
        # removed least recently used (o3), now o2 is least recently used
        cache._remove_lru(1)
        sorted_objs = cache._last_used_objs()
        assert [e[0] for e in sorted_objs] == ["o2", "o1"]
        # now load o2 (previously least recently used)
        with cache.load("o2"):
            pass
        sleep_for_fs()
        # and ensure that removing the lru removes "o1" now and keeps "o2"
        cache._remove_lru(1)
        sorted_objs = cache._last_used_objs()
        assert [e[0] for e in sorted_objs] == ["o2"]
        # removing last obj
        cache._remove_lru(1)
        sorted_objs = cache._last_used_objs()
        assert sorted_objs == []
        # and keep removing is fine
        cache._remove_lru(1)
        assert sorted_objs == []
