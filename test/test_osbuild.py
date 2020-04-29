import json
import os
import unittest

import osbuild
import osbuild.meta


class TestDescriptions(unittest.TestCase):
    def test_canonical(self):
        """Degenerate case. Make sure we always return the same canonical
        description when passing empty or null values."""

        cases = [
            {},
            {"assembler": None},
            {"stages": []},
            {"build": {}},
            {"build": None}
        ]
        for pipeline in cases:
            with self.subTest(pipeline):
                self.assertEqual(osbuild.load(pipeline, {}).description(), {})

    def test_stage(self):
        name = "org.osbuild.test"
        options = {"one": 1}
        cases = [
            (osbuild.Stage(name, {}, None, None, {}), {"name": name}),
            (osbuild.Stage(name, {}, None, None, None), {"name": name}),
            (osbuild.Stage(name, {}, None, None, options), {"name": name, "options": options}),
        ]
        for stage, description in cases:
            with self.subTest(description):
                self.assertEqual(stage.description(), description)

    def test_assembler(self):
        name = "org.osbuild.test"
        options = {"one": 1}
        cases = [
            (osbuild.Assembler(name, None, None, {}), {"name": name}),
            (osbuild.Assembler(name, None, None, None), {"name": name}),
            (osbuild.Assembler(name, None, None, options), {"name": name, "options": options}),
        ]
        for assembler, description in cases:
            with self.subTest(description):
                self.assertEqual(assembler.description(), description)

    def test_pipeline(self):
        build = osbuild.Pipeline("org.osbuild.test")
        build.add_stage("org.osbuild.test", {}, {"one": 1})

        pipeline = osbuild.Pipeline("org.osbuild.test", build)
        pipeline.add_stage("org.osbuild.test", {}, {"one": 2})
        pipeline.set_assembler("org.osbuild.test")

        self.assertEqual(pipeline.description(), {
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
                "name": "org.osbuild.test"
            }
            })

    def test_stageinfo(self):
        def list_stages(base, klass):
            return [(klass, f) for f in os.listdir(base) if f.startswith("org.osbuild")]

        stages = list_stages("stages", "Stage")
        stages += list_stages("assemblers", "Assembler")

        for stage in stages:
            klass, name = stage
            try:
                info = osbuild.meta.StageInfo.load(os.curdir, klass, name)
                schema = osbuild.meta.Schema(info.schema, name)
                res = schema.check()
                if not res:
                    err = "\n  ".join(str(e) for e in res)
                    self.fail(str(res) + "\n  " + err)
            except json.decoder.JSONDecodeError as e:
                msg = f"{klass} '{name}' has invalid STAGE_OPTS\n\t" + str(e)
                self.fail(msg)

    def test_validation(self):
        index = osbuild.meta.Index(os.curdir)

        # an empty manifest is OK
        res = osbuild.meta.validate({}, index)
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

        res = osbuild.meta.validate(totally_invalid, index)
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

        res = osbuild.meta.validate(no_runner, index)
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

        res = osbuild.meta.validate(no_runner_extra, index)
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

        res = osbuild.meta.validate(stage_check, index)
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

        res = osbuild.meta.validate(assembler_check, index)
        self.assertEqual(res.valid, False)
        self.assertEqual(len(res), 2)
        lst = res[".pipeline.assembler.options"]
        self.assertEqual(len(lst), 1)  #  missing "filename"
        lst = res[".pipeline.assembler.options.compression"]
        self.assertEqual(len(lst), 1)  #  wrong compression method


if __name__ == "__main__":
    unittest.main()
