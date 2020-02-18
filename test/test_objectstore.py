import os
import shutil
import tempfile
import unittest

from pathlib import Path
from osbuild import objectstore


class TestObjectStore(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.store = os.getenv("OSBUILD_TEST_STORE")
        if not cls.store:
            cls.store = tempfile.mkdtemp(prefix="osbuild-test-", dir="/var/tmp")

    @classmethod
    def tearDownClass(cls):
        if not os.getenv("OSBUILD_TEST_STORE"):
            shutil.rmtree(cls.store)

    def test_basic(self):
        # always use a temporary store so item counting works
        with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
            object_store = objectstore.ObjectStore(tmp)
            with object_store.new() as tree:
                path = tree.write()
                p = Path(f"{path}/A")
                p.touch()
                object_store.commit(tree, "a")

            assert os.path.exists(f"{object_store.refs}/a")
            assert os.path.exists(f"{object_store.refs}/a/A")
            assert len(os.listdir(object_store.refs)) == 1
            assert len(os.listdir(object_store.objects)) == 1
            assert len(os.listdir(f"{object_store.refs}/a/")) == 1

            with object_store.new() as tree:
                path = tree.write()
                p = Path(f"{path}/A")
                p.touch()
                p = Path(f"{path}/B")
                p.touch()
                object_store.commit(tree, "b")

            assert os.path.exists(f"{object_store.refs}/b")
            assert os.path.exists(f"{object_store.refs}/b/B")

            assert len(os.listdir(object_store.refs)) == 2
            assert len(os.listdir(object_store.objects)) == 2
            assert len(os.listdir(f"{object_store.refs}/b/")) == 2

    def test_duplicate(self):
        with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
            object_store = objectstore.ObjectStore(tmp)
            with object_store.new() as tree:
                path = tree.write()
                p = Path(f"{path}/A")
                p.touch()
                object_store.commit(tree, "a")

            with object_store.new() as tree:
                path = tree.write()
                shutil.copy2(f"{object_store.refs}/a/A",
                             f"{path}/A")
                object_store.commit(tree, "b")

            assert os.path.exists(f"{object_store.refs}/a")
            assert os.path.exists(f"{object_store.refs}/a/A")
            assert os.path.exists(f"{object_store.refs}/b/A")

            assert len(os.listdir(object_store.refs)) == 2
            assert len(os.listdir(object_store.objects)) == 1
            assert len(os.listdir(f"{object_store.refs}/a/")) == 1
            assert len(os.listdir(f"{object_store.refs}/b/")) == 1

    def test_snapshot(self):
        object_store = objectstore.ObjectStore(self.store)
        with object_store.new() as tree:
            path = tree.write()
            p = Path(f"{path}/A")
            p.touch()
            object_store.commit(tree, "a")
            path = tree.write()
            p = Path(f"{path}/B")
            p.touch()
            object_store.commit(tree, "b")

        # check the references exist
        assert os.path.exists(f"{object_store.refs}/a")
        assert os.path.exists(f"{object_store.refs}/b")

        # check the contents of the trees
        assert os.path.exists(f"{object_store.refs}/a/A")
        assert not os.path.exists(f"{object_store.refs}/a/B")

        assert os.path.exists(f"{object_store.refs}/b/A")
        assert os.path.exists(f"{object_store.refs}/b/B")


if __name__ == "__main__":
    unittest.main()
