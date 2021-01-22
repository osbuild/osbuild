#
# Basic tests for a collection of osbuild modules.
#

import json
import os
import pathlib
import sys
import tempfile
import unittest

import osbuild
import osbuild.meta
from osbuild.monitor import NullMonitor
from osbuild.objectstore import ObjectStore
from osbuild.pipeline import Manifest, detect_host_runner
from .. import test


class TestDescriptions(unittest.TestCase):

    @unittest.skipUnless(test.TestBase.can_bind_mount(), "root-only")
    def test_stage_run(self):
        index = osbuild.meta.Index(os.curdir)
        info = index.get_module_info("Stage", "org.osbuild.noop")
        stage = osbuild.Stage(info, {}, None, None, {})

        with tempfile.TemporaryDirectory() as tmpdir:

            data = pathlib.Path(tmpdir, "data")
            storedir = pathlib.Path(tmpdir, "store")
            root = pathlib.Path("/")
            runner = detect_host_runner()
            monitor = NullMonitor(sys.stderr.fileno())
            libdir = os.path.abspath(os.curdir)
            store = ObjectStore(storedir)
            data.mkdir()

            res = stage.run(data, runner, root, store, monitor, libdir)

        self.assertEqual(res.success, True)
        self.assertEqual(res.id, stage.id)

    def test_manifest(self):
        index = osbuild.meta.Index(os.curdir)

        info = index.get_module_info("Stage", "org.osbuild.noop")

        manifest = Manifest()

        # each pipeline gets a noop stage with different
        # options so that their ids are different
        build = manifest.add_pipeline("build", None, None)
        build.add_stage(info, {"option": 1})

        tree = manifest.add_pipeline("tree",
                                     "org.osbuild.linux",
                                     build.id)
        tree.add_stage(info, {"option": 2})

        assmelber = manifest.add_pipeline("assembler",
                                          "org.osbuild.inux",
                                          build.id)
        assmelber.add_stage(info, {"option": 3})

        self.assertEqual(len(manifest.pipelines), 3)

        self.assertIn("build", manifest.pipelines)
        self.assertIn("tree", manifest.pipelines)
        self.assertIn("assembler", manifest.pipelines)

        self.assertIn("build", manifest)
        self.assertIn("tree", manifest)
        self.assertIn("assembler", manifest)

        # make sure the order is correct
        lst = ["build", "tree", "assembler"]
        for a, b in zip(manifest.pipelines, lst):
            self.assertEqual(a, b)

        for a, b in zip(manifest, [build, tree, assmelber]):
            self.assertEqual(a.name, b.name)

        # check we get exceptions on unknown names
        with self.assertRaises(KeyError):
            _ = manifest.pipelines["foo"]

        with self.assertRaises(KeyError):
            _ = manifest["foo"]

        # check helper functions
        #  access by name
        check = manifest["build"]
        self.assertEqual(build.name, check.name)

        check = manifest["tree"]
        self.assertEqual(tree.name, check.name)

        check = manifest["assembler"]
        self.assertEqual(assmelber.name, check.name)

        #  `None` return for unknown items
        check = manifest.get("foo")
        self.assertIsNone(check)

        #  id based access
        for i in [build, tree, assmelber]:
            check = manifest[i.id]
            self.assertEqual(i.name, check.name)

    def test_moduleinfo(self):
        index = osbuild.meta.Index(os.curdir)

        modules = []
        for klass in ("Assembler", "Input", "Source", "Stage"):
            mods = index.list_modules_for_class(klass)
            modules += [(klass, module) for module in mods]

        self.assertTrue(modules)

        for module in modules:
            klass, name = module
            try:
                info = osbuild.meta.ModuleInfo.load(os.curdir, klass, name)
                schema = osbuild.meta.Schema(info.schema, name)
                res = schema.check()
                if not res:
                    err = "\n  ".join(str(e) for e in res)
                    self.fail(str(res) + "\n  " + err)
            except json.decoder.JSONDecodeError as e:
                msg = f"{klass} '{name}' has invalid STAGE_OPTS\n\t" + str(e)
                self.fail(msg)

    def test_schema(self):
        schema = osbuild.meta.Schema(None)
        self.assertFalse(schema)

        schema = osbuild.meta.Schema({"type": "bool"})  # should be 'boolean'
        self.assertFalse(schema.check().valid)
        self.assertFalse(schema)

        schema = osbuild.meta.Schema({"type": "array", "minItems": 3})
        self.assertTrue(schema.check().valid)
        self.assertTrue(schema)

        res = schema.validate([1, 2])
        self.assertFalse(res)
        res = schema.validate([1, 2, 3])
        self.assertTrue(res)
