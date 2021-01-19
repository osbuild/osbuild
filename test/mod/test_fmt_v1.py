#
# Tests specific for version 1 of the format
#

import os
import unittest
from typing import Dict

import osbuild
import osbuild.meta
from osbuild.formats import v1 as fmt


BASIC_PIPELINE = {
    "pipeline": {
        "build": {
            "pipeline": {
                "stages": [
                    {
                        "name": "org.osbuild.test",
                        "options": {"one": 1}
                    }
                ]
            },
            "runner": "org.osbuild.test"
        },
        "stages": [
            {
                "name": "org.osbuild.test",
                "options": {"one": 2}
            }
        ],
        "assembler": {
            "name": "org.osbuild.noop"
        }
    }
}


class TestFormatV1(unittest.TestCase):

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

    def test_load(self):
        # Load a pipeline and check the resulting manifest
        def check_stage(have: osbuild.Stage, want: Dict):
            self.assertEqual(have.name, want["name"])
            self.assertEqual(have.options, want["options"])

        index = osbuild.meta.Index(os.curdir)

        description = BASIC_PIPELINE

        # load the manifest description, that will check all
        # the stages can be found in the index and have valid
        # arguments, i.e. the schema is correct

        manifest = fmt.load(description, index)
        self.assertIsNotNone(manifest)

        # We have to have a build pipeline and a main pipeline
        self.assertTrue(manifest.pipelines)
        self.assertTrue(len(manifest.pipelines) == 2)

        build = description["pipeline"]["build"]
        pl = manifest.pipelines[0]
        have = pl.stages[0]
        want = build["pipeline"]["stages"][0]
        check_stage(have, want)

        runner = build["runner"]

        # main pipeline is the next one
        pl = manifest.pipelines[1]
        have = pl.stages[0]
        want = description["pipeline"]["stages"][0]
        self.assertEqual(pl.runner, runner)
        check_stage(have, want)

        # the assembler
        have = pl.assembler
        want = description["pipeline"]["assembler"]
        self.assertEqual(have.name, want["name"])

    def test_pipeline(self):
        index = osbuild.meta.Index(os.curdir)

        test_info = index.get_module_info("Stage", "org.osbuild.test")
        build = osbuild.Pipeline("org.osbuild.test")
        build.add_stage(test_info, {"one": 1})

        pipeline = osbuild.Pipeline("org.osbuild.test", build.tree_id)
        pipeline.add_stage(test_info, {"one": 2})
        info = index.get_module_info("Assembler", "org.osbuild.noop")
        pipeline.set_assembler(info)

        manifest = osbuild.Manifest([build, pipeline], {})

        self.assertEqual(fmt.describe(manifest), BASIC_PIPELINE)

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
