import importlib.util
import json
import os
import unittest

import osbuild

class TestDescriptions(unittest.TestCase):
    def test_canonical(self):
        """Degenerate case. Make sure we always return the same canonical
        description when passing empty or null values."""

        cases = [
            {},
            { "assembler": None },
            { "stages": [] },
            { "build": {} },
            { "build": None }
        ]
        for pipeline in cases:
            with self.subTest(pipeline):
                self.assertEqual(osbuild.load(pipeline).description(), {})

    def test_stage(self):
        name = "org.osbuild.test"
        options = { "one": 1 }
        cases = [
            (osbuild.Stage(name, None, None, {}), {"name": name}),
            (osbuild.Stage(name, None, None, None), {"name": name}),
            (osbuild.Stage(name, None, None, options), {"name": name, "options": options}),
        ]
        for stage, description in cases:
            with self.subTest(description):
                self.assertEqual(stage.description(), description)

    def test_assembler(self):
        name = "org.osbuild.test"
        options = { "one": 1 }
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
        build.add_stage("org.osbuild.test", { "one": 1 })

        pipeline = osbuild.Pipeline("org.osbuild.test", build)
        pipeline.add_stage("org.osbuild.test", { "one": 2 })
        pipeline.set_assembler("org.osbuild.test")

        self.assertEqual(pipeline.description(), {
              "build": {
                "pipeline": {
                  "stages": [
                    {
                      "name": "org.osbuild.test",
                      "options": { "one": 1 }
                    }
                  ]
                },
                "runner": "org.osbuild.test"
              },
              "stages": [
                {
                  "name": "org.osbuild.test",
                  "options": { "one": 2 }
                }
              ],
              "assembler": {
                "name": "org.osbuild.test"
              }
            })

    def test_stageinfo(self):
        def list_stages(base):
            return [(base, f) for f in os.listdir(base) if f.startswith("org.osbuild")]

        def load_module(base, name):
            loader = importlib.machinery.SourceFileLoader(name, f"{base}/{name}")
            spec = importlib.util.spec_from_loader(loader.name, loader)
            mod = importlib.util.module_from_spec(spec)
            loader.exec_module(mod)
            return mod

        stages = list_stages("stages")
        stages += list_stages("assemblers")

        for stage in stages:
            base, name = stage
            m = load_module(base, name)
            try:
                json.loads("{" + m.STAGE_OPTS + "}")
            except json.decoder.JSONDecodeError as e:
                msg = f"Stage '{base}/{name}' has invalid STAGE_OPTS\n\t" + str(e)
                self.fail(msg)


if __name__ == "__main__":
    unittest.main()
