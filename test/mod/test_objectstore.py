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
    return os.path.exists(os.path.join(obj, path))


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

            with tree.write() as path:
                p = Path(path, "A")
                p.touch()
            # consumes the object, puts it into read mode
            object_store.commit(tree, "a")

            assert tree.mode == objectstore.Object.Mode.READ

            assert object_store.contains("a")
            assert store_path(object_store, "a", "A")

            assert len(os.listdir(object_store.refs)) == 1
            assert len(os.listdir(object_store.objects)) == 1

            tree = object_store.new("b")
            with tree.write() as path:
                p = Path(path, "A")
                p.touch()
                p = Path(path, "B")
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
                with tree.write() as path:
                    p = Path(path, "A")
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
                with tree.write() as path, \
                        open(os.path.join(path, "data"), "w",
                             encoding="utf-8") as f:
                    f.write(data)
                    st = os.fstat(f.fileno())
                    data_inode = st.st_ino

                # commit the object as "x", making a copy
                store.commit(tree, "x", clone=True)

                # check that "data" got indeed copied
                tree = store.get("x")
                assert tree is not None

                with tree.read() as path:
                    with open(os.path.join(path, "data"), "r",
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
                with tree.write() as path, \
                        open(os.path.join(path, "data"), "w", encoding="utf8") as f:
                    f.write(data)
                    st = os.fstat(f.fileno())
                    data_inode = st.st_ino

                # commit the object as "a"
                store.commit(tree, "a")
                assert len(os.listdir(store.refs)) == 1

                # check that "data" is still the very
                # same file after committing
                with tree.read() as path, \
                        open(os.path.join(path, "data"), "r", encoding="utf8") as f:
                    st = os.fstat(f.fileno())
                    self.assertEqual(st.st_ino, data_inode)
                    data_read = f.read()
                    self.assertEqual(data, data_read)

    def test_object_base(self):
        with objectstore.ObjectStore(self.store) as store:
            assert len(os.listdir(store.refs)) == 0
            assert len(os.listdir(store.objects)) == 0

            base = store.new("a")
            with base.write() as path:
                p = Path(path, "A")
                p.touch()
                store.commit(base, "a")

            assert store.contains("a")
            assert store_path(store, "a", "A")

            tree = store.new("b")
            tree.init(base)

            with tree.write() as path:
                p = Path(path, "B")
                p.touch()

            tree.finalize()

            with tree.read() as path:
                assert os.path.exists(f"{path}/A")
                assert os.path.exists(f"{path}/B")

    def test_snapshot(self):
        with objectstore.ObjectStore(self.store) as store:
            tree = store.new("b")
            with tree.write() as path:
                p = Path(path, "A")
                p.touch()

            assert not store.contains("a")
            store.commit(tree, "a", clone=True)
            assert store.contains("a")

            with tree.write() as path:
                p = Path(path, "B")
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

    def test_host_tree(self):
        object_store = objectstore.ObjectStore(self.store)
        host = objectstore.HostTree(object_store)

        # check we cannot call `write`
        with self.assertRaises(ValueError):
            with host.write() as _:
                pass

        # check we actually cannot write to the path
        with host.read() as path:
            p = Path(path, "osbuild-test-file")
            with self.assertRaises(OSError):
                p.touch()

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

            path = client.read_tree("42")
            assert path is None

            obj = store.new("42")
            with obj.write() as path:
                p = Path(path, "file.txt")
                p.write_text("osbuild")

                p = Path(path, "directory")
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

            # The tree is being read via the client, should
            # not be able to write to it
            with self.assertRaises(ValueError):
                with obj.write() as _:
                    pass
