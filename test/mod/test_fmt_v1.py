#
# Tests specific for version 1 of the format
#

import os
import pathlib
import sys
import tempfile
import unittest
from typing import Dict

import osbuild
import osbuild.meta
from osbuild.formats import v1 as fmt
from osbuild.monitor import NullMonitor
from osbuild.objectstore import ObjectStore

from .. import test

BASIC_PIPELINE = {
    "sources": {
        "org.osbuild.files": {
            "urls": {
                "sha256:6eeebf21f245bf0d6f58962dc49b6dfb51f55acb6a595c6b9cbe9628806b80a4":
                "https://internet/curl-7.69.1-1.fc32.x86_64.rpm",
            }
        },
        "org.osbuild.ostree": {
            "commits": {
                "439911411ce7868a7b058c2a660e421991eb2df10e2bdce1fa559bd4390105d1": {
                    "remote": {
                        "url": "file:///repo",
                        "gpgkeys": ["data"]
                    }
                }
            }
        }
    },
    "pipeline": {
        "build": {
            "pipeline": {
                "build": {
                    "pipeline": {
                        "stages": [
                            {
                                "name": "org.osbuild.noop",
                                "options": {"zero": 0}
                            }
                        ]
                    },
                    "runner": "org.osbuild.linux"
                },
                "stages": [
                    {
                        "name": "org.osbuild.noop",
                        "options": {"one": 1}
                    }
                ]
            },
            "runner": "org.osbuild.linux"
        },
        "stages": [
            {
                "name": "org.osbuild.noop",
                "options": {"one": 2}
            }
        ],
        "assembler": {
            "name": "org.osbuild.noop"
        }
    }
}


class TestFormatV1(unittest.TestCase):

    @staticmethod
    def build_manifest(manifest: osbuild.pipeline.Manifest, tmpdir: str):
        """Build a manifest and return the result"""
        storedir = pathlib.Path(tmpdir, "store")
        monitor = NullMonitor(sys.stderr.fileno())
        libdir = os.path.abspath(os.curdir)

        with ObjectStore(storedir) as store:
            res = manifest.build(store, manifest.pipelines, monitor, libdir)

        return res

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
            self.assertEqual(have.options, want.get("options", {}))

        index = osbuild.meta.Index(os.curdir)

        description = BASIC_PIPELINE

        # load the manifest description, that will check all
        # the stages can be found in the index and have valid
        # arguments, i.e. the schema is correct
        manifest = fmt.load(description, index)
        self.assertIsNotNone(manifest)

        # We have to have two build pipelines and a main pipeline
        self.assertTrue(manifest.pipelines)
        self.assertTrue(len(manifest.pipelines) == 4)

        # access the individual pipelines via their names

        # the inner most build pipeline
        build = description["pipeline"]["build"]["pipeline"]["build"]
        pl = manifest["build-build"]
        have = pl.stages[0]
        want = build["pipeline"]["stages"][0]
        check_stage(have, want)

        runner = build["runner"]

        # the build pipeline for the 'tree' pipeline
        build = description["pipeline"]["build"]
        pl = manifest["build"]
        have = pl.stages[0]
        want = build["pipeline"]["stages"][0]
        self.assertEqual(pl.runner.name, runner)
        check_stage(have, want)

        runner = build["runner"]

        # the main, aka 'tree', pipeline
        pl = manifest["tree"]
        have = pl.stages[0]
        want = description["pipeline"]["stages"][0]
        self.assertEqual(pl.runner.name, runner)
        check_stage(have, want)

        # the assembler pipeline
        pl = manifest["assembler"]
        have = pl.stages[0]
        want = description["pipeline"]["assembler"]
        self.assertEqual(pl.runner.name, runner)
        check_stage(have, want)

    def test_describe(self):
        index = osbuild.meta.Index(os.curdir)

        manifest = fmt.load(BASIC_PIPELINE, index)
        self.assertIsNotNone(manifest)

        self.assertEqual(fmt.describe(manifest), BASIC_PIPELINE)

    def test_format_info(self):
        index = osbuild.meta.Index(os.curdir)

        lst = index.list_formats()
        self.assertIn("osbuild.formats.v1", lst)

        # an empty manifest is format "1"
        info = index.detect_format_info({})
        self.assertEqual(info.version, "1")
        self.assertEqual(info.module, fmt)

        # the basic test manifest
        info = index.detect_format_info(BASIC_PIPELINE)
        self.assertEqual(info.version, "1")
        self.assertEqual(info.module, fmt)

    # pylint: disable=too-many-statements
    @unittest.skipUnless(test.TestBase.can_bind_mount(), "root-only")
    def test_format_output(self):
        """Test that output formatting is as expected"""
        index = osbuild.meta.Index(os.curdir)

        description = {
            "pipeline": {
                "stages": [
                    {
                        "name": "org.osbuild.noop"
                    },
                    {
                        "name": "org.osbuild.error"
                    }
                ]
            }
        }

        manifest = fmt.load(description, index)
        self.assertIsNotNone(manifest)

        with tempfile.TemporaryDirectory() as tmpdir:
            res = self.build_manifest(manifest, tmpdir)

        self.assertIsNotNone(res)
        result = fmt.output(manifest, res)
        print(result)
        self.assertIsNotNone(result)
        self.assertIn("success", result)
        self.assertFalse(result["success"])
        self.assertIn("stages", result)
        stages = result["stages"]
        self.assertEqual(len(stages), 2)
        self.assertTrue(stages[0]["success"])
        self.assertFalse(stages[1]["success"])

        # check we get results for the build pipeline
        description = {
            "pipeline": {
                "build": {
                    "pipeline": {
                        "stages": [
                            {
                                "name": "org.osbuild.error"
                            }
                        ]
                    },
                    "runner": "org.osbuild.linux",
                    "stages": [
                        {
                            "name": "org.osbuild.noop"
                        }
                    ]
                }
            }
        }

        manifest = fmt.load(description, index)
        self.assertIsNotNone(manifest)

        with tempfile.TemporaryDirectory() as tmpdir:
            res = self.build_manifest(manifest, tmpdir)

        self.assertIsNotNone(res)
        result = fmt.output(manifest, res)
        self.assertIsNotNone(result)
        self.assertIn("success", result)
        self.assertFalse(result["success"])

        self.assertIn("build", result)
        self.assertIn("success", result["build"])
        self.assertFalse(result["build"]["success"])

        # check we get results for the assembler pipeline
        description = {
            "pipeline": {
                "stages": [
                    {
                        "name": "org.osbuild.noop"
                    },
                ],
                "assembler": {
                    "name": "org.osbuild.error"
                }
            }
        }

        manifest = fmt.load(description, index)
        self.assertIsNotNone(manifest)

        with tempfile.TemporaryDirectory() as tmpdir:
            res = self.build_manifest(manifest, tmpdir)

        self.assertIsNotNone(res)
        result = fmt.output(manifest, res)
        self.assertIsNotNone(result)

        self.assertIn("assembler", result)
        self.assertIn("success", result["assembler"])
        self.assertFalse(result["assembler"]["success"])

        # check the overall result is False as well
        self.assertIn("success", result)
        self.assertFalse(result["success"], result)

        # check we get all the output nodes for a successful build
        description = {
            "pipeline": {
                "stages": [
                    {
                        "name": "org.osbuild.noop"
                    },
                ],
                "assembler": {
                    "name": "org.osbuild.noop"
                }
            }
        }

        manifest = fmt.load(description, index)
        self.assertIsNotNone(manifest)

        with tempfile.TemporaryDirectory() as tmpdir:
            res = self.build_manifest(manifest, tmpdir)

        self.assertIsNotNone(res)
        result = fmt.output(manifest, res)
        self.assertIsNotNone(result)

        self.assertIn("stages", result)
        for stage in result["stages"]:
            self.assertIn("success", stage)
            self.assertTrue(stage["success"])

        self.assertIn("assembler", result)
        self.assertIn("success", result["assembler"])
        self.assertTrue(result["assembler"]["success"])

    def test_validation(self):
        index = osbuild.meta.Index(os.curdir)

        # an empty manifest is OK
        res = fmt.validate({}, index)
        self.assertEqual(res.valid, True)

        # the basic test manifest
        res = fmt.validate(BASIC_PIPELINE, index)
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
        self.assertEqual(len(lst), 1)  # missing rootfs
        lst = res[".pipeline.stages[0].options.uefi"]
        self.assertEqual(len(lst), 1)  # missing "osname"

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
        self.assertEqual(len(lst), 1)  # missing "filename"
        lst = res[".pipeline.assembler.options.compression"]
        self.assertEqual(len(lst), 1)  # wrong compression method
