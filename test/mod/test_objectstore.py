#
# Tests for the 'osbuild.objectstore' module.
#

import contextlib
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from osbuild import objectstore

from .. import test


def store_path(store: objectstore.ObjectStore, ref: str, path: str) -> bool:
    if not store.contains(ref):
        return False
    obj = store.resolve_ref(ref)
    if not obj or not os.path.exists(obj):
        return False
    return os.path.exists(os.path.join(obj, "data", "tree", path))


@unittest.skipUnless(test.TestBase.can_bind_mount(), "root-only")
class TestObjectStore(unittest.TestCase):

    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="osbuild-test-", dir="/var/tmp")

    def tearDown(self):
        shutil.rmtree(self.store)

    def test_basic(self):
        # always use a temporary store so item counting works
        with objectstore.ObjectStore(self.store) as object_store:
            # No objects or references should be in the store
            assert len(os.listdir(object_store.refs)) == 0
            assert len(os.listdir(object_store.objects)) == 0

            tree = object_store.new("a")

            # new object should be in write mode
            assert tree.mode == objectstore.Object.Mode.WRITE

            p = Path(tree, "A")
            p.touch()

            # consumes the object, puts it into read mode
            object_store.commit(tree, "a")

            assert tree.mode == objectstore.Object.Mode.READ

            assert object_store.contains("a")
            assert store_path(object_store, "a", "A")

            assert len(os.listdir(object_store.refs)) == 1
            assert len(os.listdir(object_store.objects)) == 1

            tree = object_store.new("b")
            p = Path(tree, "A")
            p.touch()
            p = Path(tree, "B")
            p.touch()

            # consumes the object, puts it into read mode
            object_store.commit(tree, "b")

            assert object_store.contains("b")
            assert store_path(object_store, "b", "B")

            assert len(os.listdir(object_store.refs)) == 2
            assert len(os.listdir(object_store.objects)) == 2
            # assert len(os.listdir(f"{object_store.refs}/b/")) == 2

            self.assertEqual(object_store.resolve_ref(None), None)
            self.assertEqual(object_store.resolve_ref("a"),
                             f"{object_store.refs}/a")

            tree = object_store.get("b")
            assert tree is not None
            assert tree.mode == objectstore.Object.Mode.READ

    def test_cleanup(self):
        # always use a temporary store so item counting works
        with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
            with objectstore.ObjectStore(tmp) as object_store:
                tree = object_store.new("a")
                self.assertEqual(len(os.listdir(object_store.tmp)), 1)
                p = Path(tree, "A")
                p.touch()

            # there should be no temporary Objects dirs anymore
            self.assertEqual(len(os.listdir(object_store.tmp)), 0)

    def test_commit_clone(self):
        # operate with a clean object store
        with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
            # sample data to be used for read, write checks
            data = "23"

            with objectstore.ObjectStore(tmp) as store:
                assert len(os.listdir(store.refs)) == 0

                tree = store.new("a")
                with open(os.path.join(tree, "data"), "w",
                          encoding="utf-8") as f:
                    f.write(data)
                    st = os.fstat(f.fileno())
                    data_inode = st.st_ino

                # commit the object as "x", making a copy
                store.commit(tree, "x")

                # check that "data" got indeed copied
                tree = store.get("x")
                assert tree is not None

                with open(os.path.join(tree, "data"), "r",
                          encoding="utf-8") as f:
                    st = os.fstat(f.fileno())
                    self.assertNotEqual(st.st_ino, data_inode)
                    data_read = f.read()
                    self.assertEqual(data, data_read)

    def test_commit_consume(self):
        # operate with a clean object store
        with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
            # sample data to be used for read, write checks
            data = "23"

            with objectstore.ObjectStore(tmp) as store:
                assert len(os.listdir(store.refs)) == 0

                tree = store.new("a")
                with open(os.path.join(tree, "data"), "w", encoding="utf8") as f:
                    f.write(data)
                    st = os.fstat(f.fileno())
                    data_inode = st.st_ino

                # commit the object as "a"
                store.commit(tree, "a")
                assert len(os.listdir(store.refs)) == 1

                # check that "data" is still the very
                # same file after committing
                with open(os.path.join(tree, "data"), "r", encoding="utf8") as f:
                    st = os.fstat(f.fileno())
                    self.assertEqual(st.st_ino, data_inode)
                    data_read = f.read()
                    self.assertEqual(data, data_read)

    def test_object_base(self):
        with objectstore.ObjectStore(self.store) as store:
            assert len(os.listdir(store.refs)) == 0
            assert len(os.listdir(store.objects)) == 0

            base = store.new("a")
            p = Path(base, "A")
            p.touch()
            store.commit(base, "a")

            assert store.contains("a")
            assert store_path(store, "a", "A")

            tree = store.new("b")
            tree.init(base)

            p = Path(tree, "B")
            p.touch()

            tree.finalize()

            assert os.path.exists(os.path.join(tree, "A"))
            assert os.path.exists(os.path.join(tree, "B"))

    def test_snapshot(self):
        with objectstore.ObjectStore(self.store) as store:
            tree = store.new("b")
            p = Path(tree, "A")
            p.touch()

            assert not store.contains("a")
            store.commit(tree, "a")  # store via "a", creates a clone
            assert store.contains("a")

            p = Path(tree, "B")
            p.touch()
            store.commit(tree, "b")

            # check the references exist
            assert os.path.exists(f"{store.refs}/a")
            assert os.path.exists(f"{store.refs}/b")

            # check the contents of the trees
            assert store_path(store, "a", "A")
            assert not store_path(store, "a", "B")
            assert store_path(store, "b", "A")
            assert store_path(store, "b", "B")

    def test_metadata(self):

        # test metadata object directly first
        with tempfile.TemporaryDirectory() as tmp:
            md = objectstore.Object.Metadata(tmp)

            assert os.fspath(md) == tmp

            with self.assertRaises(KeyError):
                with md.read("a"):
                    pass

            # do not write anything to the file, it should not get stored
            with md.write("a"):
                pass

            assert len(list(os.scandir(tmp))) == 0

            # also we should not write anything if an exception was raised
            with self.assertRaises(AssertionError):
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
            with self.assertRaises(KeyError):
                with md.read("a"):
                    pass

            md.set("a", data)
            assert md.get("a") == data
    def test_host_tree(self):
        with objectstore.ObjectStore(self.store) as store:
            host = store.host_tree

            assert host.tree
            assert os.fspath(host)

            # check we actually cannot write to the path
            p = Path(host.tree, "osbuild-test-file")
            with self.assertRaises(OSError):
                p.touch()
                print("FOO")

        # We cannot access the tree property after cleanup
        with self.assertRaises(AssertionError):
            _ = host.tree

    # pylint: disable=too-many-statements
    def test_store_server(self):

        with contextlib.ExitStack() as stack:

            store = objectstore.ObjectStore(self.store)
            stack.enter_context(stack)

            tmpdir = tempfile.TemporaryDirectory()
            tmpdir = stack.enter_context(tmpdir)

            server = objectstore.StoreServer(store)
            stack.enter_context(server)

            client = objectstore.StoreClient(server.socket_address)

            have = client.source("org.osbuild.files")
            want = os.path.join(self.store, "sources")
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

            mountpoint = Path(tmpdir, "mountpoint")
            mountpoint.mkdir()

            assert store.contains("42")
            path = client.read_tree_at("42", mountpoint)
            assert Path(path) == mountpoint
            filepath = Path(mountpoint, "file.txt")
            assert filepath.exists()
            txt = filepath.read_text(encoding="utf8")
            assert txt == "osbuild"

            # check we can mount subtrees via `read_tree_at`

            filemount = Path(tmpdir, "file")
            filemount.touch()

            path = client.read_tree_at("42", filemount, "/file.txt")
            filepath = Path(path)
            assert filepath.is_file()
            txt = filepath.read_text(encoding="utf8")
            assert txt == "osbuild"

            dirmount = Path(tmpdir, "dir")
            dirmount.mkdir()

            path = client.read_tree_at("42", dirmount, "/directory")
            dirpath = Path(path)
            assert dirpath.is_dir()

            # check proper exceptions are raised for non existent
            # mount points and sub-trees

            with self.assertRaises(RuntimeError):
                nonexistent = os.path.join(tmpdir, "nonexistent")
                _ = client.read_tree_at("42", nonexistent)

            with self.assertRaises(RuntimeError):
                _ = client.read_tree_at("42", tmpdir, "/nonexistent")
