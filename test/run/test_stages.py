#
# Runtime tests for the individual stages.
#

import difflib
import glob
import json
import os
import pprint
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from typing import Dict

from osbuild.util import selinux
from .. import initrd
from .. import test


def have_sfdisk_with_json():
    r = subprocess.run(["sfdisk", "--version"],
                       stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE,
                       encoding="utf-8",
                       check=False)

    if r.returncode != 0:
        return False

    data = r.stdout.strip()
    vstr = data.split(" ")[-1]
    ver = list(map(int, vstr.split(".")))
    return ver[0] >= 2 and ver[1] >= 27


def find_stage(result, stageid):
    build = result.get("build")
    if build:
        stage = find_stage(build, stageid)
        if stage:
            return stage

    for stage in result.get("stages", []):
        if stage["id"] == stageid:
            return stage
    return None


def make_stage_tests(klass):
    path = os.path.join(test.TestBase.locate_test_data(), "stages")
    for t in glob.glob(f"{path}/*/diff.json"):
        test_path = os.path.dirname(t)
        test_name = os.path.basename(test_path).replace("-", "_")
        setattr(klass, f"test_{test_name}",
                lambda s, path=test_path: s.run_stage_diff_test(path))
    return klass


@unittest.skipUnless(test.TestBase.have_test_data(), "no test-data access")
@unittest.skipUnless(test.TestBase.have_tree_diff(), "tree-diff missing")
@unittest.skipUnless(test.TestBase.can_bind_mount(), "root-only")
@make_stage_tests
class TestStages(test.TestBase):

    def assertTreeDiffsEqual(self, tree_diff1, tree_diff2):
        """
        Asserts two tree diffs for equality.

        Before assertion, the two trees are sorted, therefore order of files
        doesn't matter.

        There's a special rule for asserting differences where we don't
        know the exact before/after value. This is useful for example if
        the content of file is dependent on current datetime. You can use this
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

    def assertMetadata(self, metadata: Dict, result: Dict):
        """Assert all of `metadata` is found in `result`.

        Metadata must be a dictionary with stage ids as keys and
        the metadata as values. For each of those stage, metadata
        pairs the corresponding stage is looked up in the result
        and its metadata compared with the one given in metadata.
        """
        for stageid, want in metadata.items():
            stage = find_stage(result, stageid)
            if stage is None:
                js = json.dumps(result, indent=2)
                self.fail(f"stage {stageid} not found in results:\n{js}\n")
            have = stage["metadata"]
            if have != want:
                diff = difflib.ndiff(pprint.pformat(have).splitlines(),
                                     pprint.pformat(want).splitlines())
                txt = "\n".join(diff)
                path = f"/tmp/osbuild.metadata.{stageid}.json"
                with open(path, "w") as f:
                    json.dump(have, f, indent=2)
                self.fail(f"metadata for {stageid} differs:\n{txt}\n{path}")

    @classmethod
    def setUpClass(cls):
        cls.store = os.getenv("OSBUILD_TEST_STORE")
        if not cls.store:
            cls.store = tempfile.mkdtemp(prefix="osbuild-test-", dir="/var/tmp")

    @classmethod
    def tearDownClass(cls):
        if not os.getenv("OSBUILD_TEST_STORE"):
            shutil.rmtree(cls.store)

    def setUp(self):
        self.osbuild = test.OSBuild(cache_from=self.store)

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

                result = osb.compile(data, checkpoints=checkpoints)
                return context, result

            ctx_a, _ = run(f"{test_dir}/a.json")
            ctx_b, res = run(f"{test_dir}/b.json")
            ctx_a = ctx_a or tempfile.TemporaryDirectory()
            ctx_b = ctx_b or tempfile.TemporaryDirectory()

            with ctx_a as tree1, ctx_b as tree2:
                actual_diff = self.tree_diff(tree1, tree2)

            with open(f"{test_dir}/diff.json") as f:
                expected_diff = json.load(f)

            self.assertTreeDiffsEqual(expected_diff, actual_diff)

            md_path = os.path.join(test_dir, "metadata.json")
            if os.path.exists(md_path):
                with open(md_path, "r") as f:
                    metadata = json.load(f)

                self.assertMetadata(metadata, res)

            # cache the downloaded data for the sources by copying
            # it to self.cache, which is going to be used to initialize
            # the osbuild cache with.
            osb.copy_source_data(self.store, "org.osbuild.files")

    def test_dracut(self):
        datadir = self.locate_test_data()
        base = os.path.join(datadir, "stages/dracut")

        with open(f"{base}/vanilla.json", "r") as f:
            refs = json.load(f)

        with self.osbuild as osb:
            with open(f"{base}/template.json", "r") as f:
                manifest = f.read()

            tree = osb.treeid_from_manifest(manifest)
            osb.compile(manifest, checkpoints=[tree])

            with osb.map_object(tree) as tree:
                for name, want in refs.items():
                    image = initrd.Initrd(f"{tree}/boot/{name}")
                    have = image.as_dict()

                    for key in ["modules", "kmods"]:
                        a = set(have[key])
                        b = set(want[key])
                        self.assertEqual(a, b, msg=key)

            # cache the downloaded data for the files source
            osb.copy_source_data(self.store, "org.osbuild.files")

    def test_selinux(self):
        datadir = self.locate_test_data()
        testdir = os.path.join(datadir, "stages", "selinux")

        def load_manifest(manifest_name):
            with open(os.path.join(datadir, f"manifests/{manifest_name}")) as f:
                manifest = json.load(f)
                return manifest

        with self.osbuild as osb:

            for t in glob.glob(f"{testdir}/test_*.json"):
                manifest = load_manifest("f34-base.json")
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

            # cache the downloaded data for the files source
            osb.copy_source_data(self.store, "org.osbuild.files")

    def test_tar(self):
        datadir = self.locate_test_data()
        testdir = os.path.join(datadir, "stages", "tar")

        with open(os.path.join(testdir, "tar.json"), "r") as f:
            manifest = f.read()

        with self.osbuild as osb:
            treeid = osb.treeid_from_manifest(manifest)

            osb.compile(manifest, checkpoints=["tree"])

            ctx = osb.map_object(treeid)
            with ctx as tree:
                tp = os.path.join(tree, "tarfile.tar")
                assert os.path.exists(tp)
                assert tarfile.is_tarfile(tp)
                tf = tarfile.open(tp)
                names = tf.getnames()
                assert "testfile" in names
                assert "." not in names

                # Check that we do not create entries with a `./` prefix
                # since the `root-node` option is specified
                dot_slash = list(filter(lambda x: x.startswith("./"), names))
                assert not dot_slash

            # cache the downloaded data for the files source
            osb.copy_source_data(self.store, "org.osbuild.files")

    @unittest.skipUnless(have_sfdisk_with_json(), "Need sfdisk with JSON support")
    def test_parted(self):
        datadir = self.locate_test_data()
        testdir = os.path.join(datadir, "stages", "parted")

        imgname = "disk.img"

        with open(os.path.join(testdir, "parted.json"), "r") as f:
            manifest = f.read()

        with open(os.path.join(testdir, f"{imgname}.json"), "r") as f:
            want = json.load(f)

        with self.osbuild as osb:
            treeid = osb.treeid_from_manifest(manifest)

            osb.compile(manifest, checkpoints=["tree"])

            ctx = osb.map_object(treeid)
            with ctx as tree:
                target = os.path.join(tree, imgname)

                assert os.path.exists(target)

                r = subprocess.run(["sfdisk", "--json", target],
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   encoding="utf-8",
                                   check=False)

                have = json.loads(r.stdout)

            table = have["partitiontable"]

            # remove entries that are not stable across `parted`
            # invocations: "device", "id" and uuids in general
            if "device" in table:
                del table["device"]
            if "id" in table:
                del table["id"]

            for p in table["partitions"]:
                if "uuid" in p:
                    del p["uuid"]
                p["node"] = os.path.basename(p["node"])

            self.assertEqual(have, want)

            # cache the downloaded data for the files source
            osb.copy_source_data(self.store, "org.osbuild.files")
