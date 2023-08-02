#
# Tests for the 'osbuild.util.fscache' module.
#

# pylint: disable=protected-access

import json
import os
import tempfile

import pytest

from osbuild.util import fscache


@pytest.fixture(name="tmpdir")
def tmpdir_fixture():
    with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
        yield tmp


def test_calculate_size(tmpdir):
    #
    # Test the `_calculate_size()` helper and verify it only includes file
    # content in its calculation.
    #

    os.mkdir(os.path.join(tmpdir, "dir"))

    assert fscache.FsCache._calculate_size(os.path.join(tmpdir, "dir")) == 0

    with open(os.path.join(tmpdir, "dir", "file"), "x", encoding="utf8") as f:
        pass

    assert fscache.FsCache._calculate_size(os.path.join(tmpdir, "dir")) == 0

    with open(os.path.join(tmpdir, "dir", "file"), "w", encoding="utf8") as f:
        f.write("foobar")

    assert fscache.FsCache._calculate_size(os.path.join(tmpdir, "dir")) == 6


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
    assert fscache.FsCacheInfo.from_json(
        {
            "creation-boot-id": "0" * 32,
        }
    ) == fscache.FsCacheInfo(creation_boot_id="0" * 32)
    assert fscache.FsCacheInfo.from_json(
        {
            "creation-boot-id": "0" * 32,
            "maximum-size": 1024,
        }
    ) == fscache.FsCacheInfo(creation_boot_id="0" * 32, maximum_size=1024)
    assert fscache.FsCacheInfo.from_json(
        {
            "creation-boot-id": "0" * 32,
            "maximum-size": 1024,
        }
    ) == fscache.FsCacheInfo(creation_boot_id="0" * 32, maximum_size=1024)
    assert fscache.FsCacheInfo.from_json(
        {
            "creation-boot-id": "0" * 32,
            "unknown0": "foobar",
            "unknown1": ["foo", "bar"],
        }
    ) == fscache.FsCacheInfo(creation_boot_id="0" * 32)


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
        cache.info = cache.info._replace(maximum_size=1024)

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
