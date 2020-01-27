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

    def test_snapshot(self):
        object_store = objectstore.ObjectStore(self.store)
        with object_store.new("b") as tree:
            p = Path(f"{tree}/A")
            p.touch()
            object_store.snapshot(tree, "a")
            p = Path(f"{tree}/B")
            p.touch()

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
