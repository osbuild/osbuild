import difflib
import json
import os
import pprint
import tempfile
import unittest

from . import test


class TestDescriptions(unittest.TestCase, test.TestBase):

    def assertTreeDiffsEqual(self, tree_diff1, tree_diff2):
        """
        Asserts two tree diffs for equality.

        Before assertion, the two trees are sorted, therefore order of files
        doesn't matter.

        There's a special rule for asserting differences where we don't
        know the exact before/after value. This is useful for example if
        the content of file is dependant on current datetime. You can use this
        feature by putting null value in difference you don't care about.

        Example:
            "/etc/shadow": {content: ["sha256:xxx", null]}

            In this case the after content of /etc/shadow doesn't matter.
            The only thing that matters is the before content and that
            the content modification happened.
        """

        def _sorted_tree(tree):
            sorted_tree = json.loads(json.dumps(tree, sort_keys=True))
            sorted_tree["added_files"] = sorted(sorted_tree["added_files"])
            sorted_tree["deleted_files"] = sorted(sorted_tree["deleted_files"])

            return sorted_tree

        tree_diff1 = _sorted_tree(tree_diff1)
        tree_diff2 = _sorted_tree(tree_diff2)

        def raise_assertion(msg):
            diff = '\n'.join(
                difflib.ndiff(
                    pprint.pformat(tree_diff1).splitlines(),
                    pprint.pformat(tree_diff2).splitlines(),
                )
            )
            raise AssertionError(f"{msg}\n\n{diff}")

        self.assertEqual(tree_diff1['added_files'], tree_diff2['added_files'])
        self.assertEqual(tree_diff1['deleted_files'], tree_diff2['deleted_files'])

        if len(tree_diff1['differences']) != len(tree_diff2['differences']):
            raise_assertion('length of differences different')

        for (file1, differences1), (file2, differences2) in \
                zip(tree_diff1['differences'].items(), tree_diff2['differences'].items()):

            if file1 != file2:
                raise_assertion(f"filename different: {file1}, {file2}")

            if len(differences1) != len(differences2):
                raise_assertion("length of file differences different")

            for (difference1_kind, difference1_values), (difference2_kind, difference2_values) in \
                    zip(differences1.items(), differences2.items()):
                if difference1_kind != difference2_kind:
                    raise_assertion(f"different difference kinds: {difference1_kind}, {difference2_kind}")

                if difference1_values[0] is not None \
                        and difference2_values[0] is not None \
                        and difference1_values[0] != difference2_values[0]:
                    raise_assertion(f"before values are different: {difference1_values[0]}, {difference2_values[0]}")

                if difference1_values[1] is not None \
                        and difference2_values[1] is not None \
                        and difference1_values[1] != difference2_values[1]:
                    raise_assertion(f"after values are different: {difference1_values[1]}, {difference2_values[1]}")

    def setUp(self):
        self.osbuild = test.OSBuild(self)

    def run_stage_test(self, test_dir: str):
        with self.osbuild as osb:

            def run(path):
                checkpoints = []
                context = None

                with open(path, "r") as f:
                    data = f.read()

                tree = osb.treeid_from_manifest(data)
                if tree:
                    checkpoints += [tree]
                    context = osb.map_object(tree)

                osb.compile(data, checkpoints=checkpoints)
                return context

            ctx_a = run(f"{test_dir}/a.json")
            ctx_b = run(f"{test_dir}/b.json")
            ctx_a = ctx_a or tempfile.TemporaryDirectory()
            ctx_b = ctx_b or tempfile.TemporaryDirectory()

            with ctx_a as tree1, ctx_b as tree2:
                actual_diff = self.tree_diff(tree1, tree2)

            with open(f"{test_dir}/diff.json") as f:
                expected_diff = json.load(f)

            self.assertTreeDiffsEqual(expected_diff, actual_diff)


def generate_test_case(path):
    @unittest.skipUnless(test.TestBase.have_tree_diff(), "tree-diff missing")
    def test_case(self):
        self.run_stage_test(path)

    return test_case


def init_tests():
    test_dir = 'test/stages_tests'
    for name in os.listdir(test_dir):
        setattr(TestDescriptions, f"test_{name}", generate_test_case(f"{test_dir}/{name}"))


init_tests()
