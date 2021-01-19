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
from osbuild.pipeline import detect_host_runner
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
