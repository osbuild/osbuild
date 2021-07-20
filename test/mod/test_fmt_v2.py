#
# Tests specific for version 2 of the format
#

import os
import unittest

import osbuild
import osbuild.meta


BASIC_PIPELINE = {
    "version": "2",
    "sources": {
        "org.osbuild.curl": {
            "items": {
                "sha256:6eeebf21f245bf0d6f58962dc49b6dfb51f55acb6a595c6b9cbe9628806b80a4":
                "https://internet/curl-7.69.1-1.fc32.x86_64.rpm",
            }
        },
        "org.osbuild.ostree": {
            "items": {
                "439911411ce7868a7b058c2a660e421991eb2df10e2bdce1fa559bd4390105d1": {
                    "remote": {
                        "url": "file:///repo",
                        "gpgkeys": ["data"]
                    }
                }
            }
        }
    },
    "pipelines": [
        {
            "name": "build",
            "runner": "org.osbuild.linux",
            "stages": [
                {
                    "type": "org.osbuild.noop",
                    "options": {"zero": 0}
                }
            ]
        },
        {
            "name": "tree",
            "build": "name:build",
            "stages": [
                {
                    "type": "org.osbuild.noop",
                    "options": {"one": 1}
                }
            ]
        },
        {
            "name": "assembler",
            "build": "name:build",
            "stages": [
                {
                    "type": "org.osbuild.noop",
                    "options": {"one": 3},
                    "inputs": {
                        "tree": {
                            "type": "org.osbuild.tree",
                            "origin": "org.osbuild.pipeline",
                            "references": {
                                "name:tree": {}
                            }
                        }
                    },
                    "devices": {
                        "root": {
                            "type": "org.osbuild.loopback",
                            "options": {
                                "filename": "empty.img"
                            }
                        },
                        "boot": {
                            "type": "org.osbuild.loopback",
                            "options": {
                                "filename": "empty.img"
                            }
                        },
                    },
                    "mounts": {
                        "root": {
                            "type": "org.osbuild.noop",
                            "source": "root",
                            "target": "/",
                        },
                        "boot": {
                            "type": "org.osbuild.noop",
                            "source": "boot",
                            "target": "/boot",
                        },
                    }
                }
            ]
        }
    ]
}


class TestFormatV1(unittest.TestCase):
    def setUp(self):
        self.index = osbuild.meta.Index(os.curdir)
        self.maxDiff = None

    def load_manifest(self, desc):
        info = self.index.detect_format_info(desc)
        self.assertIsNotNone(info)
        fmt = info.module
        self.assertIsNotNone(fmt)
        manifest = fmt.load(desc, self.index)
        return manifest, fmt

    def assert_validation(self, result):
        if result.valid:
            return

        msg = "Validation failed:\n"
        msg += "\n".join(str(e) for e in result.errors)
        self.fail(msg)

    def test_load(self):

        desc = BASIC_PIPELINE
        info = self.index.detect_format_info(desc)
        assert info, "Failed to detect format"

        fmt = info.module
        self.assertEqual(fmt.VERSION, "2")

        manifest = fmt.load(desc, self.index)
        self.assertIsNotNone(manifest)

        self.assertTrue(manifest.pipelines)
        self.assertTrue(len(manifest.pipelines) == 3)

        build = manifest["build"]
        self.assertIsNotNone(build)

        tree = manifest["tree"]
        self.assertIsNotNone(tree)
        self.assertIsNotNone(tree.build)
        self.assertEqual(tree.build, build.id)
        self.assertEqual(tree.runner, "org.osbuild.linux")

        assembler = manifest["assembler"]
        self.assertIsNotNone(assembler)
        self.assertIsNotNone(assembler.build)
        self.assertEqual(assembler.build, build.id)
        self.assertEqual(assembler.runner, "org.osbuild.linux")

    def test_format_info(self):
        index = self.index

        lst = index.list_formats()
        self.assertIn("osbuild.formats.v2", lst)

        # the basic test manifest
        info = index.detect_format_info(BASIC_PIPELINE)
        self.assertEqual(info.version, "2")

    def test_describe(self):
        manifest, fmt = self.load_manifest(BASIC_PIPELINE)
        desc = fmt.describe(manifest)
        self.assertIsNotNone(desc)

        self.assertEqual(BASIC_PIPELINE, desc)

    def test_validation(self):
        desc = BASIC_PIPELINE
        _, fmt = self.load_manifest(desc)

        res = fmt.validate(desc, self.index)
        self.assert_validation(res)

    def test_sort_by_order(self):
        PIPELINE = {
            "version": "2",
            "pipelines": [
                {
                    "name": "test",
                    "stages": [
                        {
                            "type": "org.osbuild.noop",
                            "devices": {
                                "boot": {
                                    "type": "org.osbuild.zero",
                                    "order": 2
                                },
                                "root": {
                                    "type": "org.osbuild.zero",
                                    "order": 1
                                }
                            },
                            "mounts": {
                                "boot": {
                                    "type": "org.osbuild.noop",
                                    "source": "boot",
                                    "target": "/boot",
                                    "order": 2
                                },
                                "root": {
                                    "type": "org.osbuild.noop",
                                    "source": "root",
                                    "target": "/",
                                    "order": 1
                                },
                            }
                        }
                    ]
                }
            ]
        }

        manifest, _ = self.load_manifest(PIPELINE)
        self.assertIsNotNone(manifest)

        test = manifest["test"]
        self.assertIsNotNone(test)

        stages = test.stages
        self.assertIsNotNone(stages)
        self.assertEqual(len(stages), 1)

        stage = stages[0]
        self.assertIsNotNone(stage)

        devices = stage.devices
        self.assertIsNotNone(devices)
        self.assertEqual(len(devices), 2)
        self.assertEqual(list(devices.keys()), ["root", "boot"])

        mounts = stage.mounts
        self.assertIsNotNone(mounts)
        self.assertEqual(len(mounts), 2)
        self.assertEqual(list(mounts.keys()), ["root", "boot"])
