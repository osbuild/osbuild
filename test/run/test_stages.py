#
# Runtime tests for the individual stages.
#

import contextlib
import difflib
import functools
import glob
import json
import os
import pprint
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import xml
from collections.abc import Mapping
from typing import Callable, Dict, Optional

from osbuild.util import checksum, selinux

from .. import initrd, test


def have_sfdisk_with_json():
    r = subprocess.run(["sfdisk", "--version"],
                       stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE,
                       encoding="utf8",
                       check=False)

    if r.returncode != 0:
        return False

    data = r.stdout.strip()
    vstr = data.split(" ")[-1]

    if "-" in vstr:
        vstr = vstr.split("-")[0]

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


def mapping_is_subset(subset, other):
    """
    Recursively compares two Mapping objects and returns True if all values
    of the 'subset' Mapping are contained in the 'other' Mapping. Otherwise,
    False is returned.

    Only nested Mapping objects are compared recursively. Any other types are
    compared simply using '=='.
    """
    if isinstance(subset, Mapping) and isinstance(other, Mapping):
        for key, value in subset.items():
            if not key in other:
                return False

            other_value = other[key]

            if isinstance(value, Mapping):
                if mapping_is_subset(value, other_value):
                    continue
                return False

            if value != other_value:
                return False

        return True

    return False


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

        The first tree diff can additionally contain an `added_directories`
        array. Such an entry can be used when you care that a directory is
        added, but you don't care about its content. This means that all
        `added_files` in the second tree under the `added_directory` entry
        in the first tree will be ignored. Note that tree diffs currently
        don't distinguish between added files and added directories, so the
        `added_directories` entry is satisfied also if there's a file added
        with such a name.
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

        def path_equal_or_is_descendant(path, potential_ancestor):
            """
            :return: Returns true if path == potential_ancestor or if path is inside potential_ancestor
            """
            return path == potential_ancestor or path.startswith(potential_ancestor + "/")

        for added_dir in tree_diff1.get('added_directories', []):
            original = tree_diff2['added_files']

            filtered = [p for p in original if not path_equal_or_is_descendant(p, added_dir)]

            if len(filtered) == len(original):
                raise_assertion(f'{added_dir} was not added')

            tree_diff2['added_files'] = filtered

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
                with open(path, "w", encoding="utf8") as f:
                    json.dump(have, f, indent=2)
                self.fail(f"metadata for {stageid} differs:\n{txt}\n{path}")

    @classmethod
    def setUpClass(cls):
        cls.store = os.getenv("OSBUILD_TEST_STORE")
        if not cls.store:
            cls.store = tempfile.mkdtemp(prefix="osbuild-test-", dir="/var/tmp")

        osbuild = test.OSBuild(cache_from=cls.store)
        # pylint: disable=unnecessary-dunder-call
        cls.osbuild = osbuild.__enter__()

    @classmethod
    def tearDownClass(cls):
        # pylint: disable=unnecessary-dunder-call
        cls.osbuild.__exit__(None, None, None)
        if not os.getenv("OSBUILD_TEST_STORE"):
            shutil.rmtree(cls.store)

    def run_stage_diff_test(self, test_dir: str):
        with contextlib.ExitStack() as stack:
            osb = self.osbuild

            out_a = stack.enter_context(tempfile.TemporaryDirectory(dir="/var/tmp"))
            _ = osb.compile_file(os.path.join(test_dir, "a.json"),
                                 checkpoints=["tree"],
                                 exports=["tree"], output_dir=out_a)

            out_b = stack.enter_context(tempfile.TemporaryDirectory(dir="/var/tmp"))
            res = osb.compile_file(os.path.join(test_dir, "b.json"),
                                   checkpoints=["tree"],
                                   exports=["tree"], output_dir=out_b)

            tree1 = os.path.join(out_a, "tree")
            tree2 = os.path.join(out_b, "tree")

            actual_diff = self.tree_diff(tree1, tree2)

            with open(os.path.join(test_dir, "diff.json"), encoding="utf8") as f:
                expected_diff = json.load(f)

            self.assertTreeDiffsEqual(expected_diff, actual_diff)

            md_path = os.path.join(test_dir, "metadata.json")
            if os.path.exists(md_path):
                with open(md_path, "r", encoding="utf8") as f:
                    metadata = json.load(f)

                self.assertMetadata(metadata, res)

    def test_dracut(self):
        datadir = self.locate_test_data()
        base = os.path.join(datadir, "stages/dracut")

        with open(f"{base}/vanilla.json", "r", encoding="utf8") as f:
            refs = json.load(f)

        with tempfile.TemporaryDirectory(dir="/var/tmp") as outdir:
            osb = self.osbuild

            osb.compile_file(f"{base}/template.json",
                             checkpoints=["tree"],
                             exports=["tree"],
                             output_dir=outdir)
            tree = os.path.join(outdir, "tree")

            for name, want in refs.items():
                image = initrd.Initrd(f"{tree}/boot/{name}")
                have = image.as_dict()

                for key in ["modules", "kmods"]:
                    a = set(have[key])
                    b = set(want[key])
                    self.assertEqual(a, b, msg=key)

    def test_selinux(self):
        datadir = self.locate_test_data()
        testdir = os.path.join(datadir, "stages", "selinux")

        def load_manifest(manifest_name):
            with open(os.path.join(datadir, f"manifests/{manifest_name}"), encoding="utf8") as f:
                manifest = json.load(f)
                return manifest

        with tempfile.TemporaryDirectory(dir="/var/tmp") as outdir:
            osb = self.osbuild

            for t in glob.glob(f"{testdir}/test_*.json"):
                manifest = load_manifest("f34-base.json")
                with open(t, encoding="utf8") as f:
                    check = json.load(f)
                manifest["pipeline"]["stages"].append({
                    "name": "org.osbuild.selinux",
                    "options": check["options"]
                })

                jsdata = json.dumps(manifest)
                osb.compile(jsdata,
                            checkpoints=["tree"],
                            exports=["tree"],
                            output_dir=outdir)
                tree = os.path.join(outdir, "tree")

                for path, want in check["labels"].items():
                    have = selinux.getfilecon(f"{tree}/{path}")
                    self.assertEqual(have, want)

    def test_qemu(self):
        datadir = self.locate_test_data()
        testdir = os.path.join(datadir, "stages", "qemu")

        checks_path = os.path.join(testdir, "checks.json")
        checks = {}
        with open(checks_path, encoding="utf8") as f:
            checks = json.load(f)

        for image_name, test_data in checks.items():
            with tempfile.TemporaryDirectory(dir="/var/tmp") as outdir:
                osb = self.osbuild
                osb.compile_file(os.path.join(testdir, "qemu.json"),
                                 exports=[image_name],
                                 output_dir=outdir)

                tree = os.path.join(outdir, image_name)
                ip = os.path.join(tree, image_name)
                assert os.path.exists(ip)
                assert os.path.isfile(ip)

                qemu_img_run = subprocess.run(
                    ["qemu-img", "info", "--output=json", ip],
                    stdout=subprocess.PIPE,
                    check=True,
                    encoding="utf8"
                )

                qemu_img_out = json.loads(qemu_img_run.stdout)
                self.assertTrue(mapping_is_subset(test_data, qemu_img_out),
                                ("Test data is not a subset of the qemu-img output: "
                                 f"{test_data} not <= {qemu_img_run.stdout}"))

    def test_tar(self):
        datadir = self.locate_test_data()
        testdir = os.path.join(datadir, "stages", "tar")

        with tempfile.TemporaryDirectory(dir="/var/tmp") as outdir:
            osb = self.osbuild
            osb.compile_file(os.path.join(testdir, "tar.json"),
                             exports=["tree"],
                             output_dir=outdir)

            tree = os.path.join(outdir, "tree")
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

    @unittest.skipUnless(have_sfdisk_with_json(), "Need sfdisk with JSON support")
    def _test_partitioning_stage(self, stage_name, sfdisk_out_filter_fn: Optional[Callable[[Dict], Dict]] = None):
        """
        Helper function for testing partitioning stages.

        :param stage_name: Name of the partitioning stage to test
        :param sfdisk_out_filter_fn: Optional function to filter the output of sfdisk
               before comparing it with the expected output.
        """
        datadir = self.locate_test_data()
        testdir = os.path.join(datadir, "stages", stage_name)

        imgname = "disk.img"

        with open(os.path.join(testdir, f"{imgname}.json"), "r", encoding="utf8") as f:
            want = json.load(f)

        with tempfile.TemporaryDirectory(dir="/var/tmp") as outdir:
            osb = self.osbuild

            osb.compile_file(os.path.join(testdir, f"{stage_name}.json"),
                             checkpoints=["tree"],
                             exports=["tree"],
                             output_dir=outdir)

            target = os.path.join(outdir, "tree", imgname)

            assert os.path.exists(target)

            r = subprocess.run(["sfdisk", "--json", target],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               encoding="utf8",
                               check=False)

            have = json.loads(r.stdout)

            if sfdisk_out_filter_fn is not None:
                have = sfdisk_out_filter_fn(have)

            # Old versions of sfdisk (e.g. on RHEL-8), do not include
            # the 'sectorsize' in the output, so we delete it from the
            # expected output if it is not present in the actual output
            if "sectorsize" not in have["partitiontable"]:
                del want["partitiontable"]["sectorsize"]

            self.assertEqual(want, have)

    def test_parted(self):
        def filter_sfdisk_output(sfdisk_output: Dict) -> Dict:
            table = sfdisk_output["partitiontable"]
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
            return sfdisk_output

        self._test_partitioning_stage("parted", filter_sfdisk_output)

    def test_sgdisk(self):
        def filter_sfdisk_output(sfdisk_output: Dict) -> Dict:
            table = sfdisk_output["partitiontable"]
            # remove entries that are not stable across `parted`
            # invocations: "device", "id"
            if "device" in table:
                del table["device"]
            for p in table["partitions"]:
                p["node"] = os.path.basename(p["node"])
            return sfdisk_output

        self._test_partitioning_stage("sgdisk", filter_sfdisk_output)

    def test_sfdisk(self):
        def filter_sfdisk_output(sfdisk_output: Dict) -> Dict:
            table = sfdisk_output["partitiontable"]
            # remove entries that are not stable across `sfdisk`
            # invocations: "device"
            if "device" in table:
                del table["device"]
            for p in table["partitions"]:
                p["node"] = os.path.basename(p["node"])
            return sfdisk_output

        self._test_partitioning_stage("sfdisk", filter_sfdisk_output)

    def test_ovf(self):
        datadir = self.locate_test_data()
        testdir = os.path.join(datadir, "stages", "ovf")

        with tempfile.TemporaryDirectory(dir="/var/tmp") as outdir:
            osb = self.osbuild
            osb.compile_file(os.path.join(testdir, "ovf.json"), exports=["vmdk"], output_dir=outdir)

            vmdk = os.path.join(outdir, "vmdk", "image.vmdk")
            assert os.path.isfile(vmdk)

            ovf = os.path.join(outdir, "vmdk", "image.ovf")
            assert os.path.isfile(ovf)

            # verify the manifest
            mf = os.path.join(outdir, "vmdk", "image.mf")
            assert os.path.isfile(mf)

            with open(mf, "r", encoding="utf-8") as f:
                ovf_line = f.readline().split(" ")
                assert ovf_line[0] == f"SHA256({os.path.basename(ovf)})="
                assert ovf_line[1].rstrip() == checksum.hexdigest_file(ovf, "sha256")
                vmdk_line = f.readline().split(" ")
                assert vmdk_line[0] == f"SHA256({os.path.basename(vmdk)})="
                assert vmdk_line[1].rstrip() == checksum.hexdigest_file(vmdk, "sha256")

            ovf_tree = xml.etree.ElementTree.parse(ovf)
            ovf_tree_root = ovf_tree.getroot()

            ovf_tree_file = ovf_tree_root[0][0]
            assert ovf_tree_file.attrib["{http://schemas.dmtf.org/ovf/envelope/1}href"] == "image.vmdk"
            assert ovf_tree_file.attrib["{http://schemas.dmtf.org/ovf/envelope/1}size"] == str(os.stat(vmdk).st_size)

            ovf_tree_disk = ovf_tree_root[1][1]
            res = subprocess.run(["qemu-img", "info", "--output=json", vmdk], check=True, stdout=subprocess.PIPE)
            capacity = ovf_tree_disk.attrib["{http://schemas.dmtf.org/ovf/envelope/1}capacity"]
            assert capacity == str(json.loads(res.stdout)["virtual-size"])
            pop_size = ovf_tree_disk.attrib["{http://schemas.dmtf.org/ovf/envelope/1}populatedSize"]
            assert pop_size == str(os.stat(vmdk).st_size)
