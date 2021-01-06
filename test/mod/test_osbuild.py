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
from osbuild.formats import v1 as fmt
from osbuild.monitor import NullMonitor
from osbuild.objectstore import ObjectStore
from osbuild.pipeline import detect_host_runner
from .. import test


class TestDescriptions(unittest.TestCase):
    def test_canonical(self):
        """Degenerate case. Make sure we always return the same canonical
        description when passing empty or null values."""

        index = osbuild.meta.Index(os.curdir)

        cases = [
            {},
            {"assembler": None},
            {"stages": []},
            {"build": {}},
            {"build": None}
        ]
        for pipeline in cases:
            manifest = {"pipeline": pipeline}
            with self.subTest(pipeline):
                desc = fmt.describe(fmt.load(manifest, index))
                self.assertEqual(desc["pipeline"], {})

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
        for klass in ("Stage", "Assembler", "Source"):
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

    def test_validation(self):
        index = osbuild.meta.Index(os.curdir)

        # an empty manifest is OK
        res = fmt.validate({}, index)
        self.assertEqual(res.valid, True)

        # something totally invalid (by Ondřej Budai)
        totally_invalid = {
            "osbuild": {
                "state": "awesome",
                "but": {
                    "input-validation": 1
                }
            }
        }

        res = fmt.validate(totally_invalid, index)
        self.assertEqual(res.valid, False)
        # The top-level 'osbuild' is an additional property
        self.assertEqual(len(res), 1)

        # This is missing the runner
        no_runner = {
            "pipeline": {
                "build": {
                    "pipeline": {}
                }
            }
        }

        res = fmt.validate(no_runner, index)
        self.assertEqual(res.valid, False)
        self.assertEqual(len(res), 1)  # missing runner
        lst = res[".pipeline.build"]
        self.assertEqual(len(lst), 1)

        # de-dup issues: the manifest checking will report
        # the extra element and the recursive build pipeline
        # check will also report that same error; make sure
        # they get properly de-duplicated
        no_runner_extra = {
            "pipeline": {
                "build": {  # missing runner
                    "pipeline": {
                        "extra": True,  # should not be there
                        "stages": [{
                            "name": "org.osbuild.chrony",
                            "options": {
                                "timeservers": "string"  # should be an array
                            }
                        }]
                    }
                }
            }
        }

        res = fmt.validate(no_runner_extra, index)
        self.assertEqual(res.valid, False)
        self.assertEqual(len(res), 3)
        lst = res[".pipeline.build.pipeline"]
        self.assertEqual(len(lst), 1)  # should only have one
        lst = res[".pipeline.build.pipeline.stages[0].options.timeservers"]
        self.assertEqual(len(lst), 1)  # should only have one

        # stage issues
        stage_check = {
            "pipeline": {
                "stages": [{
                    "name": "org.osbuild.grub2",
                    "options": {
                        "uefi": {
                            "install": False,
                            # missing "vendor"
                        },
                        # missing rootfs or root_fs_uuid
                    }
                }]
            }
        }

        res = fmt.validate(stage_check, index)
        self.assertEqual(res.valid, False)
        self.assertEqual(len(res), 2)
        lst = res[".pipeline.stages[0].options"]
        self.assertEqual(len(lst), 1)  #  missing rootfs
        lst = res[".pipeline.stages[0].options.uefi"]
        self.assertEqual(len(lst), 1)  #  missing "osname"

        assembler_check = {
            "pipeline": {
                "assembler": {
                    "name": "org.osbuild.tar",
                    "options": {
                        "compression": "foobar"
                    }
                }
            }
        }

        res = fmt.validate(assembler_check, index)
        self.assertEqual(res.valid, False)
        self.assertEqual(len(res), 2)
        lst = res[".pipeline.assembler.options"]
        self.assertEqual(len(lst), 1)  #  missing "filename"
        lst = res[".pipeline.assembler.options.compression"]
        self.assertEqual(len(lst), 1)  #  wrong compression method
