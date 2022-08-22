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
        with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
            object_store = objectstore.ObjectStore(tmp)
            # No objects or references should be in the store
            assert len(os.listdir(object_store.refs)) == 0
            assert len(os.listdir(object_store.objects)) == 0

            with object_store.new() as tree:
                with tree.write() as path:
                    p = Path(path, "A")
                    p.touch()
                object_store.commit(tree, "a")

            assert object_store.contains("a")
            assert store_path(object_store, "a", "A")

            assert len(os.listdir(object_store.refs)) == 1
            assert len(os.listdir(object_store.objects)) == 1

            with object_store.new() as tree:
                with tree.write() as path:
                    p = Path(path, "A")
                    p.touch()
                    p = Path(path, "B")
                    p.touch()
                object_store.commit(tree, "b")

            assert object_store.contains("b")
            assert store_path(object_store, "b", "B")

            assert len(os.listdir(object_store.refs)) == 2
            assert len(os.listdir(object_store.objects)) == 2
            # assert len(os.listdir(f"{object_store.refs}/b/")) == 2

            self.assertEqual(object_store.resolve_ref(None), None)
            self.assertEqual(object_store.resolve_ref("a"),
                             f"{object_store.refs}/a")

    def test_cleanup(self):
        # always use a temporary store so item counting works
        with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
            with objectstore.ObjectStore(tmp) as object_store:
                tree = object_store.new()
                self.assertEqual(len(os.listdir(object_store.tmp)), 1)
                with tree.write() as path:
                    p = Path(path, "A")
                    p.touch()
            # there should be no temporary Objects dirs anymore
            self.assertEqual(len(os.listdir(object_store.tmp)), 0)

    # pylint: disable=no-self-use
    def test_object_base(self):
        # operate with a clean object store
        with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
            object_store = objectstore.ObjectStore(tmp)
            with object_store.new() as tree:
                with tree.write() as path:
                    p = Path(path, "A")
                    p.touch()
                object_store.commit(tree, "a")

            with object_store.new() as tree:
                tree.base = "a"
                object_store.commit(tree, "b")

            with object_store.new() as tree:
                tree.base = "b"
                with tree.write() as path:
                    p = Path(path, "C")
                    p.touch()
                object_store.commit(tree, "c")

            assert store_path(object_store, "a", "A")
            assert store_path(object_store, "b", "A")
            assert store_path(object_store, "c", "A")
            assert store_path(object_store, "c", "C")

            assert len(os.listdir(object_store.refs)) == 3
            assert len(os.listdir(object_store.objects)) == 3

    def test_commit_clone(self):
        # operate with a clean object store
        with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
            # sample data to be used for read, write checks
            data = "23"

            object_store = objectstore.ObjectStore(tmp)
            assert len(os.listdir(object_store.refs)) == 0

            with object_store.new() as tree:
                path = tree.write()
                with tree.write() as path, \
                        open(os.path.join(path, "data"), "w", encoding="utf-8") as f:
                    f.write(data)
                    st = os.fstat(f.fileno())
                    data_inode = st.st_ino
                # commit the object as "x", making a copy
                object_store.commit(tree, "x", clone=True)

                # check that "data" got indeed copied
                with tree.read() as path:
                    with open(os.path.join(path, "data"), "r", encoding="utf-8") as f:
                        st = os.fstat(f.fileno())
                        self.assertNotEqual(st.st_ino, data_inode)
                        data_read = f.read()
                        self.assertEqual(data, data_read)

    def test_object_copy_on_write(self):
        # operate with a clean object store
        with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
            # sample data to be used for read, write checks
            data = "23"

            object_store = objectstore.ObjectStore(tmp)
            assert len(os.listdir(object_store.refs)) == 0

            with object_store.new() as tree:
                path = tree.write()
                with tree.write() as path, \
                        open(os.path.join(path, "data"), "w", encoding="utf8") as f:
                    f.write(data)
                    st = os.fstat(f.fileno())
                    data_inode = st.st_ino
                # commit the object as "x"
                object_store.commit(tree, "x")
                # after the commit, "x" is now the base
                # of "tree"
                self.assertEqual(tree.base, "x")
                # check that "data" is still the very
                # same file after committing
                with tree.read() as path:
                    with open(os.path.join(path, "data"), "r", encoding="utf8") as f:
                        st = os.fstat(f.fileno())
                        self.assertEqual(st.st_ino, data_inode)
                        data_read = f.read()
                        self.assertEqual(data, data_read)

            # the object referenced by "x" should act as
            # the base of a new object. As long as the
            # new one is not modified, it should have
            # the very same content
            with object_store.new(base_id="x") as tree:
                self.assertEqual(tree.base, "x")
                with tree.read() as path:
                    with open(os.path.join(path, "data"), "r", encoding="utf8") as f:
                        # copy-on-write: since we have not written
                        # to the tree yet, "data" should be the
                        # very same file as that one of object "x"
                        st = os.fstat(f.fileno())
                        self.assertEqual(st.st_ino, data_inode)
                        data_read = f.read()
                        self.assertEqual(data, data_read)
                with tree.write() as path:
                    # "data" must of course still be present
                    assert os.path.exists(os.path.join(path, "data"))
                    # but since it is a copy, have a different inode
                    st = os.stat(os.path.join(path, "data"))
                    self.assertNotEqual(st.st_ino, data_inode)
                    p = Path(path, "other_data")
                    p.touch()

    def test_object_mode(self):
        object_store = objectstore.ObjectStore(self.store)
        with object_store.new() as tree:
            # check that trying to write to a tree that is
            # currently being read from fails
            with tree.read() as _:
                with self.assertRaises(ValueError):
                    with tree.write() as _:
                        pass

                # check multiple readers are ok
                with tree.read() as _:
                    pass

                # writing should still fail
                with self.assertRaises(ValueError):
                    with tree.write() as _:
                        pass

            # Now that all readers are gone, writing should
            # work
            with tree.write() as _:
                pass

            # and back to reading, one last time
            with tree.read() as _:
                with self.assertRaises(ValueError):
                    with tree.write() as _:
                        pass

            # Only one single writer
            with tree.write() as _:
                # no other readers
                with self.assertRaises(ValueError):
                    with tree.read() as _:
                        pass

                # or other writers
                with self.assertRaises(ValueError):
                    with tree.write() as _:
                        pass

            # one more time
            with tree.write() as _:
                pass

        # tree has exited the context, it should NOT be
        # writable anymore
        with self.assertRaises(ValueError):
            with tree.write() as _:
                pass

    def test_snapshot(self):
        object_store = objectstore.ObjectStore(self.store)
        with object_store.new() as tree:
            with tree.write() as path:
                p = Path(path, "A")
                p.touch()
            assert not object_store.contains("a")
            object_store.commit(tree, "a")
            assert object_store.contains("a")
            with tree.write() as path:
                p = Path(path, "B")
                p.touch()
            object_store.commit(tree, "b")

        # check the references exist
        assert os.path.exists(f"{object_store.refs}/a")
        assert os.path.exists(f"{object_store.refs}/b")

        # check the contents of the trees
        assert store_path(object_store, "a", "A")
        assert not store_path(object_store, "a", "B")
        assert store_path(object_store, "b", "A")
        assert store_path(object_store, "b", "B")

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

            obj = store.new()
            with obj.write() as path:
                p = Path(path, "file.txt")
                p.write_text("osbuild")

                p = Path(path, "directory")
                p.mkdir()

            obj.id = "42"

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
