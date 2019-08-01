
import osbuild
import unittest


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
            (osbuild.Assembler(name, {}), {"name": name}),
            (osbuild.Assembler(name, None), {"name": name}),
            (osbuild.Assembler(name, options), {"name": name, "options": options}),
        ]
        for assembler, description in cases:
            with self.subTest(description):
                self.assertEqual(assembler.description(), description)

    def test_pipeline(self):
        build = osbuild.Pipeline()
        build.add_stage("org.osbuild.test", { "one": 1 })

        pipeline = osbuild.Pipeline(build)
        pipeline.add_stage("org.osbuild.test", { "one": 2 })
        pipeline.set_assembler("org.osbuild.test")

        self.assertEqual(pipeline.description(), {
              "build": {
                "stages": [
                  {
                    "name": "org.osbuild.test",
                    "options": { "one": 1 }
                  }
                ]
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


if __name__ == "__main__":
    unittest.main()
