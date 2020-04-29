#
# Tests for the 'osbuild.util.fscache' module.
#

import os
import tempfile
import unittest

from osbuild.util import fscache


class TestUtilFsCache(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.cache = fscache.Cache("osbuild-test-appid", self.dir.name)

    def tearDown(self):
        self.dir = self.dir.cleanup()

    def test_basic(self):
        #
        # Verify basic cache behavior. Check that non-existant entries yield
        # a cache-miss, then create an entry and verify it can be found. Lastly,
        # verify the entry cannot be re-created.
        #

        with self.cache as c:
            with self.assertRaises(fscache.Cache.MissError):
                with c.load("foo"):
                    pass

            with c.store("foo") as e:
                with open(os.path.join(e, "bar"), "x") as f:
                    f.write("foobar")

            with c.load("foo") as e:
                with open(os.path.join(e, "bar"), "r") as f:
                    assert f.read() == "foobar"

            with self.assertRaises(fscache.Cache.MissError):
                with c.store("foo"):
                    pass


    def test_no_scaffolding(self):
        #
        # Verify that the cache only creates scaffolding if really necessary.
        # Furthermore, it should behave fine without scaffolding present.
        #

        assert len(list(os.scandir(self.dir.name))) == 0

        # Verify that cache-initialization does not create scaffolding.
        with self.cache:
            pass
        assert len(list(os.scandir(self.dir.name))) == 0

        # Verify a load does not require nor create scaffolding.
        with self.cache as c:
            with self.assertRaises(fscache.Cache.MissError):
                with c.load("foobar"):
                    pass
        assert len(list(os.scandir(self.dir.name))) == 0

        # Verify a store correctly prepares scaffolding, even if it fails.
        with self.cache as c:
            with self.assertRaises(SystemError):
                with c.store("foobar"):
                    raise SystemError
        assert len(list(os.scandir(self.dir.name))) == 2
        assert len(list(os.scandir(os.path.join(self.dir.name, "refs")))) == 0
        assert len(list(os.scandir(os.path.join(self.dir.name, "objects")))) == 0

    def test_basic_locking(self):
        #
        # Verify that cache-entries are write-locked during stores, and
        # read-locked during loads.
        #

        with self.cache as c:
            with c.store("foo"):
                with self.assertRaises(fscache.Cache.MissError):
                    with c.store("foo"):
                        pass
                with self.assertRaises(fscache.Cache.MissError):
                    with c.load("foo"):
                        pass

            with c.load("foo"):
                with c.load("foo"):
                    pass
                with self.assertRaises(fscache.Cache.MissError):
                    with c.store("foo"):
                        pass
