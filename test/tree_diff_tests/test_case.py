import logging
from dataclasses import dataclass
from typing import List, Callable, Any

from test import evaluate_test
from test.tree_diff_tests.compare import compare_trees
from test.tree_diff_tests.trees import Tree


@dataclass
class TreeDiffTestCase:
    name: str
    test_cases: List[Callable[[Any], None]]
    trees: (Tree, Tree)

    def run(self):
        logging.info(f"Running tree diff test {self.name}")
        self.trees[0].build()

        if not self.trees[0].has_same_pipeline_as(self.trees[1]):
            self.trees[1].build()
        else:
            logging.info("No need to run osbuild again, the pipeline is common for both trees")

        with self.trees[0].mount() as a_tree, self.trees[1].mount() as b_tree:
            tree_diff = compare_trees(a_tree, b_tree)
            # debug only, delete before PR merge!!!
            print(tree_diff)
            for test in self.test_cases:
                evaluate_test(lambda: test(tree_diff))
