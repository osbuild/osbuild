import ast
import json
import unittest
from pathlib import Path

class TestStageInfo(unittest.TestCase):
    @staticmethod
    def iter_stages(stagedir):
        '''Yield executable files in `stagedir`'''
        for p in Path(stagedir).iterdir():
            if p.is_file() and not p.is_symlink() and p.stat().st_mode & 1:
                yield p

    @staticmethod
    def get_stage_info(stage: Path) -> dict:
        '''Return the STAGE_* variables from the given stage.'''
        # NOTE: This works for now, but stages should probably have some
        # standard way of dumping this info so we (and other higher-level
        # tools) don't have to parse the code and walk through the AST
        # to find these values.
        stage_info = {}
        with open(stage) as fobj:
            stage_ast = ast.parse(fobj.read(), filename=stage)

        # STAGE_* assignments are at the toplevel, no need to walk()
        for node in stage_ast.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Str):
                for target in node.targets:
                    if target.id.startswith("STAGE_"):
                        stage_info[target.id] = node.value.s

        return stage_info

    @staticmethod
    def parse_stage_opts(stage_opts: str) -> dict:
        if not stage_opts.lstrip().startswith('{'):
            stage_opts = '{' + stage_opts + '}'
        return json.loads(stage_opts)

    def setUp(self):
        self.topdir = Path(".") # NOTE: this could be smarter...
        self.stages_dir = self.topdir / "stages"
        self.assemblers_dir = self.topdir / "assemblers"
        self.stages = list(self.iter_stages(self.stages_dir))
        self.assemblers = list(self.iter_stages(self.assemblers_dir))

    def check_stage_info(self, stage):
        with self.subTest(check="STAGE_{INFO,DESC,OPTS} vars present"):
            stage_info = self.get_stage_info(stage)
            self.assertIn("STAGE_DESC", stage_info)
            self.assertIn("STAGE_INFO", stage_info)
            self.assertIn("STAGE_OPTS", stage_info)

        with self.subTest(check="STAGE_OPTS is valid JSON"):
            stage_opts = self.parse_stage_opts(stage_info["STAGE_OPTS"])
            self.assertIsNotNone(stage_opts)

        # NOTE: We probably want an actual JSON Schema validator but
        # a nicely basic sanity test for our current STAGE_OPTS is:
        # 1. If it's not empty, there should be a "properties" object,
        # 2. If "required" exists, each item should be a property name
        with self.subTest(check="STAGE_OPTS is valid JSON Schema"):
            if stage_opts:
                self.assertIn("properties", stage_opts)
                self.assertIsInstance(stage_opts["properties"], dict)
            for prop in stage_opts.get("required", []):
                self.assertIn(prop, stage_opts["properties"])

    def test_stage_info(self):
        for stage in self.stages:
            with self.subTest(stage=stage.name):
                self.check_stage_info(stage)
        for assembler in self.assemblers:
            with self.subTest(assembler=assembler.name):
                self.check_stage_info(assembler)
