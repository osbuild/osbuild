#
# Runtime tests for the individual stages.
#

import difflib
import glob
import json
import os
import pprint
import tempfile
import unittest

from osbuild.util import selinux
from osbuild.util import initrd
from .. import test


@unittest.skipUnless(test.TestBase.have_test_data(), "no test-data access")
@unittest.skipUnless(test.TestBase.have_tree_diff(), "tree-diff missing")
class TestStages(test.TestBase):

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

    def run_stage_diff_test(self, test_dir: str):
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

    def test_stages(self):
        path = os.path.join(self.locate_test_data(), "stages")
        for t in glob.glob(f"{path}/*/diff.json"):
            test_path = os.path.dirname(t)
            test_name = os.path.basename(test_path)
            with self.subTest(stage=test_name):
                self.run_stage_diff_test(test_path)

    def test_selinux(self):
        datadir = self.locate_test_data()
        testdir = os.path.join(datadir, "stages", "selinux")

        def load_manifest(manifest_name):
            with open(os.path.join(datadir, f"manifests/{manifest_name}")) as f:
                manifest = json.load(f)
                return manifest

        with self.osbuild as osb:

            for t in glob.glob(f"{testdir}/test_*.json"):
                manifest = load_manifest("f32-base.json")
                with open(t) as f:
                    check = json.load(f)
                manifest["pipeline"]["stages"].append({
                    "name": "org.osbuild.selinux",
                    "options": check["options"]
                })

                jsdata = json.dumps(manifest)
                treeid = osb.treeid_from_manifest(jsdata)
                osb.compile(jsdata, checkpoints=[treeid])
                ctx = osb.map_object(treeid)

                with ctx as tree:
                    for path, want in check["labels"].items():
                        have = selinux.getfilecon(f"{tree}/{path}")
                        self.assertEqual(have, want)

    def test_dracut(self):
        datadir = self.locate_test_data()
        base = os.path.join(datadir, "stages/dracut")
        name = "initramfs-5.3.7-301.fc31.x86_64.img"

        with self.osbuild as osb:

            def run_and_read(m):
                tree = osb.treeid_from_manifest(m)
                osb.compile(m, checkpoints=[tree])

                ctx = osb.map_object(tree)
                with ctx as tree:
                    path = os.path.join(tree, "boot", name)
                    img = initrd.Initrd(path)
                    return img.as_dict()

            with open(f"{base}/vanilla.json", "r") as f:
                js = json.load(f)
                self.assertIn(name, js)
                ref = js[name]

            with open(f"{base}/template.json", "r") as f:
                manifest = f.read()

            data = run_and_read(manifest)
            for key in ["modules", "kmods"]:
                a = set(ref[key])
                b = set(data[key])
                self.assertEqual(a, b)
