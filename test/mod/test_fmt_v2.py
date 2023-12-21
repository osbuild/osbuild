#
# Tests specific for version 2 of the format
#

import copy
import itertools
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
                        "var": {
                            "type": "org.osbuild.loopback",
                            "options": {
                                "filename": "empty.img",
                                "partscan": True,
                            },
                        },
                    },
                    "mounts": [
                        {
                            "name": "root",
                            "type": "org.osbuild.noop",
                            "source": "root",
                            "target": "/",
                        },
                        {
                            "name": "boot",
                            "type": "org.osbuild.noop",
                            "source": "boot",
                            "target": "/boot",
                        },
                        {
                            "name": "var",
                            "type": "org.osbuild.noop",
                            "source": "var",
                            "target": "/var",
                            "partition": 1,
                        }
                    ]
                }
            ]
        }
    ]
}

BAD_SHA = "sha256:15a654d32efaa75b5df3e2481939d0393fe1746696cc858ca094ccf8b76073cd"

BAD_REF_PIPELINE = {
    "version": "2",
    "sources": {
        "org.osbuild.curl": {
            "items": {
                "sha256:c540ca8c5e21ba5f063286c94a088af2aac0b15bc40df6fd562d40154c10f4a1": "",
            }
        }
    },
    "pipelines": [
        {
            "name": "build",
            "stages": [
                {
                    "type": "org.osbuild.rpm",
                    "inputs": {
                        "packages": {
                            "type": "org.osbuild.files",
                            "origin": "org.osbuild.source",
                            "references": {
                                BAD_SHA: {}
                            }
                        }
                    }
                }
            ]
        }
    ]
}


INPUT_REFERENCES = {
    "version": "2",
    "sources": {
        "org.osbuild.curl": {
            "items": {
                "sha256:6eeebf21f245bf0d6f58962dc49b6dfb51f55acb6a595c6b9cbe9628806b80a4":
                "https://internet/curl-7.69.1-1.fc32.x86_64.rpm",
                "sha256:184a0c274d4efa84a2f6d0a128aae87e2fa231fe9067b4a4dc8f886fa6f1dc18":
                "https://internet/kernel-5.11.12-300.fc34.x86_64.rpm"
            }
        },
    },
    "pipelines": [
        {
            "name": "os",
            "stages": [
                {
                    "type": "org.osbuild.rpm",
                    "inputs": {
                        "packages": {
                            "type": "org.osbuild.files",
                            "origin": "org.osbuild.source",
                            "references": [
                                "sha256:6eeebf21f245bf0d6f58962dc49b6dfb51f55acb6a595c6b9cbe9628806b80a4",
                                "sha256:184a0c274d4efa84a2f6d0a128aae87e2fa231fe9067b4a4dc8f886fa6f1dc18"
                            ]
                        }
                    }
                }
            ],
        },
    ]
}


class TestFormatV2(unittest.TestCase):
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
        self.assertEqual(tree.runner.name, "org.osbuild.linux")

        assembler = manifest["assembler"]
        self.assertIsNotNone(assembler)
        self.assertIsNotNone(assembler.build)
        self.assertEqual(assembler.build, build.id)
        self.assertEqual(assembler.runner.name, "org.osbuild.linux")

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

    def test_load_bad_ref_manifest(self):
        desc = BAD_REF_PIPELINE

        info = self.index.detect_format_info(desc)
        self.assertIsNotNone(info)
        fmt = info.module
        self.assertIsNotNone(fmt)

        with self.assertRaises(ValueError) as ex:
            fmt.load(desc, self.index)

        self.assertTrue(str(ex.exception).find(BAD_SHA) > -1,
                        "The unknown source reference is not included in the exception")

    def test_mounts(self):
        BASE = {
            "version": "2",

            "pipelines": [
                {
                    "name": "test",
                    "runner": "org.osbuild.linux",
                    "stages": [
                        {
                            "type": "org.osbuild.noop",
                            "options": {"zero": 0},
                            "devices": {
                                "root": {
                                    "type": "org.osbuild.loopback",
                                    "options": {
                                        "filename": "empty.img"
                                    }
                                }
                            },
                            "mounts": []
                        }
                    ]
                }
            ]
        }

        # verify the device
        pipeline = copy.deepcopy(BASE)
        stage = pipeline["pipelines"][0]["stages"][0]
        mounts = stage["mounts"]

        mounts.extend([{
            "name": "root",
            "type": "org.osbuild.noop",
            "source": "root",
            "target": "/",
        }])

        manifest, _ = self.load_manifest(pipeline)
        self.assertIsNotNone(manifest)
        test = manifest["test"]
        self.assertIsNotNone(test)
        stage = test.stages[0]
        root = stage.mounts["root"]
        self.assertIsNotNone(root)
        self.assertIsNotNone(root.device)
        self.assertEqual(root.device.name, "root")

        # duplicated mount
        pipeline = copy.deepcopy(BASE)
        stage = pipeline["pipelines"][0]["stages"][0]
        mounts = stage["mounts"]

        mounts.extend([{
            "name": "root",
            "type": "org.osbuild.noop",
            "source": "root",
            "target": "/",
        }, {
            "name": "root",
            "type": "org.osbuild.noop",
            "source": "root",
            "target": "/",
        }])

        with self.assertRaises(ValueError):
            self.load_manifest(pipeline)

        # mount without a device
        pipeline = copy.deepcopy(BASE)
        stage = pipeline["pipelines"][0]["stages"][0]
        mounts = stage["mounts"]

        mounts.extend([{
            "name": "boot",
            "type": "org.osbuild.noop",
            "source": "boot",
            "target": "/boot",
        }])

        with self.assertRaises(ValueError):
            self.load_manifest(pipeline)

    def test_mounts_with_partition(self):
        BASE = {
            "version": "2",
            "pipelines": [
                {
                    "name": "test",
                    "runner": "org.osbuild.linux",
                    "stages": [
                        {
                            "type": "org.osbuild.noop",
                            "options": {"zero": 0},
                            "devices": {
                                "root": {
                                    "type": "org.osbuild.loopback",
                                    "options": {
                                        "filename": "empty.img",
                                        "partscan": True,
                                    }
                                }
                            },
                            "mounts": [
                                {
                                    "name": "root",
                                    "type": "org.osbuild.noop",
                                    "source": "root",
                                    "target": "/",
                                    "partition": 1,
                                },
                            ],
                        }
                    ]
                }
            ]
        }

        # verify the device
        pipeline = copy.deepcopy(BASE)
        manifest, _ = self.load_manifest(pipeline)
        root_mnt = manifest["test"].stages[0].mounts["root"]
        self.assertEqual(root_mnt.device.name, "root")
        self.assertEqual(root_mnt.partition, 1)

    def test_device_sorting(self):
        fmt = self.index.get_format_info("osbuild.formats.v2").module
        assert fmt

        self_cycle = {
            "a": {"parent": "a"},
        }

        with self.assertRaises(ValueError):
            fmt.sort_devices(self_cycle)

        cycle = {
            "a": {"parent": "b"},
            "b": {"parent": "a"},
        }

        with self.assertRaises(ValueError):
            fmt.sort_devices(cycle)

        missing_parent = {
            "a": {"parent": "b"},
            "b": {"parent": "c"},
        }

        with self.assertRaises(ValueError):
            fmt.sort_devices(missing_parent)

        def ensure_sorted(devices):
            check = {}

            for name, dev in devices.items():

                parent = dev.get("parent")
                if parent:
                    assert parent in check

                check[name] = dev

            assert devices == check

        devices = {
            "a": {"parent": "d"},
            "b": {"parent": "a"},
            "c": {"parent": None},
            "d": {"parent": "c"},
        }

        for check in itertools.permutations(devices.keys()):
            before = {name: devices[name] for name in check}
            ensure_sorted(fmt.sort_devices(before))

    def check_input_references(self, desc):
        info = self.index.detect_format_info(desc)
        assert info, "Failed to detect format"

        fmt = info.module
        self.assertEqual(fmt.VERSION, "2")

        res = fmt.validate(desc, self.index)
        self.assert_validation(res)

        manifest = fmt.load(desc, self.index)
        self.assertIsNotNone(manifest)

        pl = manifest.get("os")
        assert pl is not None

        packages = pl.stages[0].inputs["packages"]
        assert packages is not None
        assert len(packages.refs) == 2

        refs = [
            "sha256:6eeebf21f245bf0d6f58962dc49b6dfb51f55acb6a595c6b9cbe9628806b80a4",
            "sha256:184a0c274d4efa84a2f6d0a128aae87e2fa231fe9067b4a4dc8f886fa6f1dc18"
        ]

        keys = list(packages.refs.keys())
        assert keys == refs

    def test_input_references(self):

        # assert that the input references are ordered properly, i.e.
        # their order is preserved as specified in the manifest

        desc = INPUT_REFERENCES
        self.check_input_references(desc)

        inputs = desc["pipelines"][0]["stages"][0]["inputs"]["packages"]
        refs = inputs["references"]

        # check references as maps
        inputs["references"] = {
            k: {} for k in refs
        }

        self.check_input_references(desc)

        # check references passed as array of objects
        inputs["references"] = [
            {"id": k, "options": {}} for k in refs
        ]
        self.check_input_references(desc)
