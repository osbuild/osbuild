import json
import os
import tempfile

from test import osbuildtest


class TestDescriptions(osbuildtest.TestCase):

    def run_stage_test(self, test_dir: str):
        pipeline1 = f"{test_dir}/a.json"
        pipeline2 = f"{test_dir}/b.json"
        tree_id1, _ = self.run_osbuild(pipeline1)
        tree_id2, _ = self.run_osbuild(pipeline2)

        with tempfile.TemporaryDirectory() as empty:
            if tree_id1:
                tree1 = self.get_path_to_store(tree_id1)
            else:
                tree1 = empty

            if tree_id2:
                tree2 = self.get_path_to_store(tree_id2)
            else:
                tree2 = empty

            actual_diff = self.run_tree_diff(tree1, tree2)

        with open(f"{test_dir}/diff.json") as f:
            expected_diff = json.load(f)

        self.assertTreeDiffsEqual(expected_diff, actual_diff)


def generate_test_case(test):
    def test_case(self):
        self.run_stage_test(test)

    return test_case


def init_tests():
    test_dir = 'test/stages_tests'
    for test in os.listdir(test_dir):
        setattr(TestDescriptions, f"test_{test}", generate_test_case(f"{test_dir}/{test}"))


init_tests()
