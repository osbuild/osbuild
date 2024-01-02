#
# Tests for the 'osbuild.objectstore' module.
#

import contextlib
import os
import tempfile
from pathlib import Path

import pytest

from osbuild import objectstore

from .. import test


def store_path(store: objectstore.ObjectStore, ref: str, path: str) -> bool:
    obj = store.get(ref)
    if not obj:
        return False
    return os.path.exists(os.path.join(obj, path))


@pytest.fixture(name="object_store")
def store_fixture():
    with tempfile.TemporaryDirectory(
        prefix="osbuild-test-",
        dir="/var/tmp",
    ) as tmp:
        with objectstore.ObjectStore(tmp) as store:
            yield store


def test_basic(object_store):
    object_store.maximum_size = 1024 * 1024 * 1024

    # No objects or references should be in the store
    assert len(os.listdir(object_store.objects)) == 0

    tree = object_store.new("a")

    # new object should be in write mode
    assert tree.mode == objectstore.Object.Mode.WRITE

    p = Path(tree, "A")
    p.touch()

    tree.finalize()  # put the object into READ mode
    assert tree.mode == objectstore.Object.Mode.READ

    # commit makes a copy, if space
    object_store.commit(tree, "a")
    assert store_path(object_store, "a", "A")

    # second object, based on the first one
    obj2 = object_store.new("b")
    obj2.init(tree)

    p = Path(obj2, "B")
    p.touch()

    obj2.finalize()  # put the object into READ mode
    assert obj2.mode == objectstore.Object.Mode.READ

    # commit always makes a copy, if space
    object_store.commit(tree, "b")

    assert object_store.contains("b")
    assert store_path(object_store, "b", "A")
    assert store_path(object_store, "b", "B")

    assert len(os.listdir(object_store.objects)) == 2

    # object should exist and should be in read mode
    tree = object_store.get("b")
    assert tree is not None
    assert tree.mode == objectstore.Object.Mode.READ


def test_cleanup(tmp_path):
    with objectstore.ObjectStore(tmp_path) as object_store:
        object_store.maximum_size = 1024 * 1024 * 1024

        stage = os.path.join(object_store, "stage")
        tree = object_store.new("a")
        assert len(os.listdir(stage)) == 1
        p = Path(tree, "A")
        p.touch()

    # there should be no temporary Objects dirs anymore
    with objectstore.ObjectStore(tmp_path) as object_store:
        assert object_store.get("A") is None


def test_metadata(tmp_path):

    # test metadata object directly first
    with tempfile.TemporaryDirectory() as tmp:
        md = objectstore.Object.Metadata(tmp)

        assert os.fspath(md) == tmp

        with pytest.raises(KeyError):
            with md.read("a"):
                pass

        # do not write anything to the file, it should not get stored
        with md.write("a"):
            pass

        assert len(list(os.scandir(tmp))) == 0

        # also we should not write anything if an exception was raised
        with pytest.raises(AssertionError):
            with md.write("a") as f:
                f.write("{}")
                raise AssertionError

        with md.write("a") as f:
            f.write("{}")

        assert len(list(os.scandir(tmp))) == 1

        with md.read("a") as f:
            assert f.read() == "{}"

    data = {
        "boolean": True,
        "number": 42,
        "string": "yes, please"
    }

    extra = {
        "extra": "data"
    }

    with tempfile.TemporaryDirectory() as tmp:
        md = objectstore.Object.Metadata(tmp)

        d = md.get("a")
        assert d is None

        md.set("a", None)
        with pytest.raises(KeyError):
            with md.read("a"):
                pass

        md.set("a", data)
        assert md.get("a") == data

    # use tmp_path fixture from here on
    with objectstore.ObjectStore(tmp_path) as store:
        store.maximum_size = 1024 * 1024 * 1024
        obj = store.new("a")
        p = Path(obj, "A")
        p.touch()

        obj.meta.set("md", data)
        assert obj.meta.get("md") == data

        store.commit(obj, "x")
        obj.meta.set("extra", extra)
        assert obj.meta.get("extra") == extra

        store.commit(obj, "a")

    with objectstore.ObjectStore(tmp_path) as store:
        obj = store.get("a")

        assert obj.meta.get("md") == data
        assert obj.meta.get("extra") == extra

        ext = store.get("x")

        assert ext.meta.get("md") == data
        assert ext.meta.get("extra") is None


@pytest.mark.skipif(not test.TestBase.can_bind_mount(), reason="Need root for bind mount")
def test_host_tree(tmp_path):
    with objectstore.ObjectStore(tmp_path) as store:
        host = store.host_tree

        assert host.tree
        assert os.fspath(host)

        # check we actually cannot write to the path
        p = Path(host.tree, "osbuild-test-file")
        with pytest.raises(OSError):
            p.touch()
            print("FOO")

    # We cannot access the tree property after cleanup
    with pytest.raises(AssertionError):
        _ = host.tree


def test_source_epoch(object_store):
    tree = object_store.new("a")
    tree.source_epoch = 946688461

    t = Path(tree)

    a = Path(tree, "A")
    a.touch()

    d = Path(tree, "d")
    d.mkdir()

    l = Path(tree, "l")
    l.symlink_to(d, target_is_directory=True)

    for i in (a, d, l, t):
        si = os.stat(i, follow_symlinks=False)
        before = int(si.st_mtime)
        assert before != tree.source_epoch

    # FINALIZING
    tree.finalize()

    for i in (a, d, l, t):
        si = os.stat(i, follow_symlinks=False)
        after = int(si.st_mtime)

        assert after != before, f"mtime not changed for {i}"
        assert after == tree.source_epoch

    baum = object_store.new("b")
    baum.init(tree)

    assert baum.created == tree.created

    b = Path(tree, "B")
    b.touch()

    si = os.stat(b, follow_symlinks=False)
    before = int(si.st_mtime)

    assert before != tree.source_epoch

    # FINALIZING
    baum.finalize()
    si = os.stat(a, follow_symlinks=False)
    after = int(si.st_mtime)

    assert after != before
    assert after == tree.source_epoch

# pylint: disable=too-many-statements


@pytest.mark.skipif(not test.TestBase.can_bind_mount(), reason="Need root for bind mount")
def test_store_server(tmp_path):
    with contextlib.ExitStack() as stack:

        store = objectstore.ObjectStore(tmp_path)
        stack.enter_context(store)

        tmp = tempfile.TemporaryDirectory()
        tmp = stack.enter_context(tmp)

        server = objectstore.StoreServer(store)
        stack.enter_context(server)

        client = objectstore.StoreClient(server.socket_address)

        have = client.source("org.osbuild.files")
        want = os.path.join(tmp_path, "sources")
        assert have.startswith(want)

        tmp = client.mkdtemp(suffix="suffix", prefix="prefix")
        assert tmp.startswith(store.tmp)
        name = os.path.basename(tmp)
        assert name.startswith("prefix")
        assert name.endswith("suffix")

        obj = store.new("42")
        p = Path(obj, "file.txt")
        p.write_text("osbuild")

        p = Path(obj, "directory")
        p.mkdir()
        obj.finalize()

        mountpoint = Path(tmp_path, "mountpoint")
        mountpoint.mkdir()

        assert store.contains("42")
        path = client.read_tree_at("42", mountpoint)
        assert Path(path) == mountpoint
        filepath = Path(mountpoint, "file.txt")
        assert filepath.exists()
        txt = filepath.read_text(encoding="utf8")
        assert txt == "osbuild"

        # check we can mount subtrees via `read_tree_at`

        filemount = Path(tmp_path, "file")
        filemount.touch()

        path = client.read_tree_at("42", filemount, "/file.txt")
        filepath = Path(path)
        assert filepath.is_file()
        txt = filepath.read_text(encoding="utf8")
        assert txt == "osbuild"

        dirmount = Path(tmp_path, "dir")
        dirmount.mkdir()

        path = client.read_tree_at("42", dirmount, "/directory")
        dirpath = Path(path)
        assert dirpath.is_dir()

        # check proper exceptions are raised for non existent
        # mount points and sub-trees

        with pytest.raises(RuntimeError):
            nonexistent = os.path.join(tmp_path, "nonexistent")
            _ = client.read_tree_at("42", nonexistent)

        with pytest.raises(RuntimeError):
            _ = client.read_tree_at("42", tmp_path, "/nonexistent")


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
def test_object_export_preserves_ownership_by_default(tmp_path, object_store):
    tree = object_store.new("a")
    p = Path(tree, "A")
    p.touch()
    os.chown(os.fspath(p), 1000, 1000)
    tree.export(tmp_path)

    expected_exported_path = Path(tmp_path, "A")
    assert expected_exported_path.exists()
    assert expected_exported_path.stat().st_uid == 1000
    assert expected_exported_path.stat().st_gid == 1000


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
def test_object_export_preserves_override(tmp_path, object_store):
    tree = object_store.new("a")
    p = Path(tree, "A")
    p.touch()
    os.chown(os.fspath(p), 1000, 1000)
    tree.export(tmp_path, skip_preserve_owner=True)

    expected_exported_path = Path(tmp_path, "A")
    assert expected_exported_path.exists()
    assert expected_exported_path.stat().st_uid == 0
    assert expected_exported_path.stat().st_gid == 0
