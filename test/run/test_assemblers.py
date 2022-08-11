#
# Runtime tests for the individual assemblers.
#

import contextlib
import hashlib
import json
import os
import subprocess
import tempfile
import unittest

from osbuild import loop
from .. import test

MEBIBYTE = 1024 * 1024


@unittest.skipUnless(test.TestBase.have_test_data(), "no test-data access")
@unittest.skipUnless(test.TestBase.can_bind_mount(), "root-only")
class TestAssemblers(test.TestBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def setUp(self):
        self.osbuild = test.OSBuild()

    @contextlib.contextmanager
    def run_assembler(self, osb, name, options, output_path):
        with open(os.path.join(self.locate_test_data(),
                               "manifests/filesystem.json")) as f:
            manifest = json.load(f)
        manifest["pipeline"] = dict(
            manifest["pipeline"],
            assembler={"name": name, "options": options}
        )
        data = json.dumps(manifest)

        treeid = osb.treeid_from_manifest(data)
        assert treeid

        with tempfile.TemporaryDirectory(dir="/var/tmp") as output_dir:
            osb.compile(data, output_dir=output_dir, exports=["assembler", "tree"])
            tree = os.path.join(output_dir, "tree")
            yield tree, os.path.join(output_dir, "assembler", output_path)

    def assertImageFile(self, filename, fmt, expected_size=None):
        info = json.loads(subprocess.check_output(["qemu-img", "info", "--output", "json", filename]))
        self.assertEqual(info["format"], fmt)
        self.assertEqual(info["virtual-size"], expected_size)

    def assertFilesystem(self, device, uuid, fstype, tree):
        output = subprocess.check_output(["blkid", "--output", "export", device], encoding="utf-8")
        blkid = dict(line.split("=") for line in output.strip().split("\n"))
        self.assertEqual(blkid["UUID"], uuid)
        self.assertEqual(blkid["TYPE"], fstype)

        with mount(device) as target_tree:
            diff = self.tree_diff(tree, target_tree)
            if fstype == 'ext4':
                added_files = ["/lost+found"]
            else:
                added_files = []
            self.assertEqual(diff["added_files"], added_files)
            self.assertEqual(diff["deleted_files"], [])
            self.assertEqual(diff["differences"], {})

    def assertGRUB2(self, device, l1hash, l2hash, size):
        m1 = hashlib.sha256()
        m2 = hashlib.sha256()
        with open(device, "rb") as d:
            sectors = d.read(size)
        self.assertEqual(len(sectors), size)
        m1.update(sectors[:440])
        m2.update(sectors[512:size])
        self.assertEqual(m1.hexdigest(), l1hash)
        self.assertEqual(m2.hexdigest(), l2hash)

    def assertPartitionTable(self, ptable, label, uuid, n_partitions, boot_partition=None):
        self.assertEqual(ptable["label"], label)
        self.assertEqual(ptable["id"][2:], uuid[:8])
        self.assertEqual(len(ptable["partitions"]), n_partitions)

        if boot_partition:
            bootable = [p.get("bootable", False) for p in ptable["partitions"]]
            self.assertEqual(bootable.count(True), 1)
            self.assertEqual(bootable.index(True) + 1, boot_partition)

    def read_partition_table(self, device):
        sfdisk = json.loads(subprocess.check_output(["sfdisk", "--json", device]))
        ptable = sfdisk["partitiontable"]
        self.assertIsNotNone(ptable)
        return ptable

    @unittest.skipUnless(test.TestBase.have_tree_diff(), "tree-diff missing")
    def test_rawfs(self):
        for fs_type in ["ext4", "xfs", "btrfs"]:
            with self.subTest(fs_type=fs_type):
                print(f"  {fs_type}", flush=True)
                options = {
                    "filename": "image.raw",
                    "root_fs_uuid": "016a1cda-5182-4ab3-bf97-426b00b74eb0",
                    "size": 1024 * MEBIBYTE,
                    "fs_type": fs_type,
                }
                with self.osbuild as osb:
                    with self.run_assembler(osb, "org.osbuild.rawfs", options, "image.raw") as (tree, image):
                        self.assertImageFile(image, "raw", options["size"])
                        self.assertFilesystem(image, options["root_fs_uuid"], fs_type, tree)

    @unittest.skipUnless(test.TestBase.have_tree_diff(), "tree-diff missing")
    def test_ostree(self):
        with self.osbuild as osb:
            with open(os.path.join(self.locate_test_data(),
                                   "manifests/fedora-ostree-commit.json")) as f:
                manifest = json.load(f)

            data = json.dumps(manifest)
            with tempfile.TemporaryDirectory(dir="/var/tmp") as output_dir:
                result = osb.compile(data, output_dir=output_dir, exports=["ostree-commit"])
                compose_file = os.path.join(output_dir, "ostree-commit", "compose.json")
                repo = os.path.join(output_dir, "ostree-commit", "repo")

                with open(compose_file) as f:
                    compose = json.load(f)
                commit_id = compose["ostree-commit"]
                ref = compose["ref"]
                rpmostree_inputhash = compose["rpm-ostree-inputhash"]
                os_version = compose["ostree-version"]
                assert commit_id
                assert ref
                assert rpmostree_inputhash
                assert os_version
                self.assertIn("metadata", result)
                metadata = result["metadata"]
                commit = metadata["ostree-commit"]
                info = commit["org.osbuild.ostree.commit"]
                self.assertIn("compose", info)
                self.assertEqual(compose, info["compose"])

                md = subprocess.check_output(
                    [
                        "ostree",
                        "show",
                        "--repo", repo,
                        "--print-metadata-key=rpmostree.inputhash",
                        commit_id
                    ], encoding="utf-8").strip()
                self.assertEqual(md, f"'{rpmostree_inputhash}'")

                md = subprocess.check_output(
                    [
                        "ostree",
                        "show",
                        "--repo", repo,
                        "--print-metadata-key=version",
                        commit_id
                    ], encoding="utf-8").strip()
                self.assertEqual(md, f"'{os_version}'")

    @unittest.skipUnless(test.TestBase.have_tree_diff(), "tree-diff missing")
    def test_qemu(self):
        loctl = loop.LoopControl()
        with self.osbuild as osb:
            for fmt in ["raw", "raw.xz", "qcow2", "vmdk", "vdi"]:
                for fs_type in ["ext4", "xfs", "btrfs"]:
                    with self.subTest(fmt=fmt, fs_type=fs_type):
                        print(f"  {fmt} {fs_type}", flush=True)
                    options = {
                        "format": fmt,
                        "filename": f"image.{fmt}",
                        "ptuuid": "b2c09a39-db93-44c5-846a-81e06b1dc162",
                        "root_fs_uuid": "aff010e9-df95-4f81-be6b-e22317251033",
                        "size": 1024 * MEBIBYTE,
                        "root_fs_type": fs_type,
                    }
                    with self.run_assembler(osb,
                                            "org.osbuild.qemu",
                                            options,
                                            f"image.{fmt}") as (tree, image):
                        if fmt == "raw.xz":
                            subprocess.run(["unxz", "--keep", "--force", image], check=True)
                            image = image[:-3]
                            fmt = "raw"
                        self.assertImageFile(image, fmt, options["size"])
                        with open_image(loctl, image, fmt) as (target, device):
                            ptable = self.read_partition_table(device)
                            self.assertPartitionTable(ptable,
                                                      "dos",
                                                      options["ptuuid"],
                                                      1,
                                                      boot_partition=1)
                            if fs_type == "btrfs":
                                l2hash = "919aad44d37aa9fdbb8cb1bbd8ce2a44e64aee76f4dceb805eaab041b7f62348"
                            elif fs_type == "xfs":
                                l2hash = "1729f531281e4c3cbcde2a39b587c9dd5334ea1335bb860905556d5b73603de6"
                            else:
                                l2hash = "24c3ad6be9a5687d5140e0bf66d25953c4f0c7eeb6aaced4cc64685f5b3cfa9e"
                            self.assertGRUB2(device,
                                             "26e3327c6b5ac9b5e21d8b86f19ff7cb4d12fb2d0406713f936997d9d89de3ee",
                                             l2hash,
                                             1024 * 1024)

                            p1 = ptable["partitions"][0]
                            ssize = ptable.get("sectorsize", 512)
                            start, size = p1["start"] * ssize, p1["size"] * ssize
                            with loop_open(loctl, target, offset=start, size=size) as dev:
                                self.assertFilesystem(dev, options["root_fs_uuid"], fs_type, tree)

    @unittest.skipUnless(test.TestBase.have_tree_diff(), "tree-diff missing")
    def test_tar(self):
        cases = [
            ("tree.tar.gz", None, ["application/x-tar"]),
            ("tree.tar.gz", "gzip", ["application/x-gzip", "application/gzip"])
        ]
        with self.osbuild as osb:
            for filename, compression, expected_mimetypes in cases:
                options = {"filename": filename}
                if compression:
                    options["compression"] = compression
                with self.run_assembler(osb,
                                        "org.osbuild.tar",
                                        options,
                                        filename) as (tree, image):
                    output = subprocess.check_output(["file", "--mime-type", image], encoding="utf-8")
                    _, mimetype = output.strip().split(": ")  # "filename: mimetype"
                    self.assertIn(mimetype, expected_mimetypes)

                    if compression:
                        continue

                    # In the non-compression case, we verify the tree's content
                    with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
                        args = [
                            "tar",
                            "--numeric-owner",
                            "--selinux",
                            "--acls",
                            "--xattrs", "--xattrs-include", "*",
                            "-xaf", image,
                            "-C", tmp]
                        subprocess.check_output(args, encoding="utf-8")
                        diff = self.tree_diff(tree, tmp)
                        self.assertEqual(diff["added_files"], [])
                        self.assertEqual(diff["deleted_files"], [])
                        self.assertEqual(diff["differences"], {})


@contextlib.contextmanager
def loop_create_device(ctl, fd, offset=None, sizelimit=None):
    lo = None
    try:
        lo = ctl.loop_for_fd(fd,
                             offset=offset,
                             sizelimit=sizelimit,
                             autoclear=True)
        yield lo
    finally:
        if lo:
            lo.close()


@contextlib.contextmanager
def loop_open(ctl, image, *, offset=None, size=None):
    with open(image, "rb") as f:
        fd = f.fileno()
        with loop_create_device(ctl, fd, offset=offset, sizelimit=size) as lo:
            yield os.path.join("/dev", lo.devname)


@contextlib.contextmanager
def mount(device):
    with tempfile.TemporaryDirectory() as mountpoint:
        subprocess.run(["mount", "-o", "ro", device, mountpoint], check=True)
        try:
            yield mountpoint
        finally:
            subprocess.run(["umount", "--lazy", mountpoint], check=True)


@contextlib.contextmanager
def open_image(ctl, image, fmt):
    with tempfile.TemporaryDirectory() as tmp:
        if fmt != "raw":
            target = os.path.join(tmp, "image.raw")
            subprocess.run(["qemu-img", "convert", "-O", "raw", image, target],
                           check=True)
        else:
            target = image

        size = os.stat(target).st_size

        with loop_open(ctl, target, offset=0, size=size) as dev:
            yield target, dev
