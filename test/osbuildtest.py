import difflib

import json
import os
import pprint
import shutil
import subprocess
import tempfile
import unittest


class TestCase(unittest.TestCase):
    """A TestCase to test running the osbuild program.

    Each test case can use `self.run_osbuild()` to run osbuild. A temporary
    store is used, which can be accessed through `self.store`. The store is
    persistent for whole test class due to performance concerns.

    To speed up local development, OSBUILD_TEST_STORE can be set to an existing
    store. Note that this might make tests dependant of each other. Do not use
    it for actual testing.
    """

    @classmethod
    def setUpClass(cls):
        cls.store = os.getenv("OSBUILD_TEST_STORE")
        if not cls.store:
            cls.store = tempfile.mkdtemp(prefix="osbuild-test-", dir="/var/tmp")

    @classmethod
    def tearDownClass(cls):
        if not os.getenv("OSBUILD_TEST_STORE"):
            shutil.rmtree(cls.store)

    def run_osbuild(self, pipeline, input=None):
        osbuild_cmd = ["python3", "-m", "osbuild", "--json", "--store", self.store, "--libdir", ".", pipeline]

        build_env = os.getenv("OSBUILD_TEST_BUILD_ENV", None)
        if build_env:
            osbuild_cmd.append("--build-env")
            osbuild_cmd.append(build_env)

        stdin = subprocess.PIPE if input else None

        p = subprocess.Popen(osbuild_cmd, encoding="utf-8", stdin=stdin, stdout=subprocess.PIPE)
        if input:
            p.stdin.write(input)
            p.stdin.close()
        try:
            r = p.wait()
            if r != 0:
                print(p.stdout.read())
            self.assertEqual(r, 0)
        except KeyboardInterrupt:
            # explicitly wait again to let osbuild clean up
            p.wait()
            raise

        result = json.load(p.stdout)
        p.stdout.close()
        return result["tree_id"], result["output_id"]

    def run_tree_diff(self, tree1, tree2):
        tree_diff_cmd = ["./tree-diff", tree1, tree2]

        r = subprocess.run(tree_diff_cmd, encoding="utf-8", stdout=subprocess.PIPE, check=True)

        return json.loads(r.stdout)

    def get_path_to_store(self, tree_id):
        return f"{self.store}/refs/{tree_id}"

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
        tree_diff1 = _sorted_tree(tree_diff1)
        tree_diff2 = _sorted_tree(tree_diff2)

        def raise_assertion(msg):
            raise TreeAssertionError(msg, tree_diff1, tree_diff2)

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


def _sorted_tree(tree):
    sorted_tree = json.loads(json.dumps(tree, sort_keys=True))
    sorted_tree["added_files"] = sorted(sorted_tree["added_files"])
    sorted_tree["deleted_files"] = sorted(sorted_tree["deleted_files"])

    return sorted_tree


class TreeAssertionError(AssertionError):
    def __init__(self, msg, tree_diff1, tree_diff2):
        diff = ('\n'.join(difflib.ndiff(
            pprint.pformat(tree_diff1).splitlines(),
            pprint.pformat(tree_diff2).splitlines())))
        super().__init__(f"{msg}\n\n{diff}")
