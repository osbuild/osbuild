#
# Runtime tests for the individual assemblers.
#

import contextlib
import glob
import hashlib
import json
import os
import subprocess
import tempfile
import time
import unittest

from .. import test


@unittest.skipUnless(test.TestBase.have_test_data(), "no test-data access")
class TestAssemblers(test.TestBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        subprocess.run(["modprobe", "nbd"], check=False)

    def setUp(self):
        self.osbuild = test.OSBuild(self)

    @contextlib.contextmanager
    def run_assembler(self, name, options, output_path):
        with self.osbuild as osb:
            with open(os.path.join(self.locate_test_data(),
                                   "manifests/fedora-boot.json")) as f:
                manifest = json.load(f)
            manifest["pipeline"] = dict(
                manifest["pipeline"],
                assembler={"name": name, "options": options}
            )
            data = json.dumps(manifest)

            treeid = osb.treeid_from_manifest(data)
            assert treeid

            osb.compile(data, checkpoints=[treeid])
            with osb.map_object(treeid) as tree, \
                 osb.map_output(output_path) as output:
                yield tree, output

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
            self.assertEqual(diff["added_files"], ["/lost+found"])
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
        options = {
            "filename": "image.raw",
            "root_fs_uuid": "016a1cda-5182-4ab3-bf97-426b00b74eb0",
            "size": 2 * 1024 * 1024 * 1024
        }
        with self.run_assembler("org.osbuild.rawfs", options, "image.raw") as (tree, image):
            self.assertImageFile(image, "raw", options["size"])
            self.assertFilesystem(image, options["root_fs_uuid"], "ext4", tree)

    @unittest.skipUnless(test.TestBase.have_tree_diff(), "tree-diff missing")
    def test_qemu(self):
        for fmt in ["raw", "raw.xz", "qcow2", "vmdk", "vdi"]:
            with self.subTest(fmt=fmt):
                print(f"  {fmt}", flush=True)
                options = {
                    "format": fmt,
                    "filename": f"image.{fmt}",
                    "ptuuid": "b2c09a39-db93-44c5-846a-81e06b1dc162",
                    "root_fs_uuid": "aff010e9-df95-4f81-be6b-e22317251033",
                    "size": 2 * 1024 * 1024 * 1024
                }
                with self.run_assembler("org.osbuild.qemu",
                                        options,
                                        f"image.{fmt}") as (tree, image):
                    if fmt == "raw.xz":
                        subprocess.run(["unxz", "--keep", "--force", image], check=True)
                        image = image[:-3]
                        fmt = "raw"
                    self.assertImageFile(image, fmt, options["size"])
                    with nbd_connect(image) as device:
                        ptable = self.read_partition_table(device)
                        self.assertPartitionTable(ptable,
                                                  "dos",
                                                  options["ptuuid"],
                                                  1,
                                                  boot_partition=1)
                        self.assertGRUB2(device,
                                         "26e3327c6b5ac9b5e21d8b86f19ff7cb4d12fb2d0406713f936997d9d89de3ee",
                                         "9b31c8fbc59602a38582988bf91c3948ae9c6f2a231ab505ea63a7005e302147",
                                         1024 * 1024)
                        self.assertFilesystem(device + "p1", options["root_fs_uuid"], "ext4", tree)

    def test_tar(self):
        cases = [
            ("tree.tar.gz", None, ["application/x-tar"]),
            ("tree.tar.gz", "gzip", ["application/x-gzip", "application/gzip"])
        ]
        for filename, compression, expected_mimetypes in cases:
            options = {"filename": filename}
            if compression:
                options["compression"] = compression
            with self.run_assembler("org.osbuild.tar",
                                    options,
                                    filename) as (_, image):
                output = subprocess.check_output(["file", "--mime-type", image], encoding="utf-8")
                _, mimetype = output.strip().split(": ") # "filename: mimetype"
                self.assertIn(mimetype, expected_mimetypes)


@contextlib.contextmanager
def mount(device):
    with tempfile.TemporaryDirectory() as mountpoint:
        subprocess.run(["mount", "-o", "ro", device, mountpoint], check=True)
        try:
            yield mountpoint
        finally:
            subprocess.run(["umount", "--lazy", mountpoint], check=True)


@contextlib.contextmanager
def nbd_connect(image):
    for device in glob.glob("/dev/nbd*"):
        r = subprocess.run(["qemu-nbd", "--connect", device, "--read-only", image], check=False).returncode
        if r == 0:
            try:
                # qemu-nbd doesn't wait for the device to be ready
                for _ in range(100):
                    if subprocess.run(["nbd-client", "--check", device],
                                      check=False,
                                      stdout=subprocess.DEVNULL).returncode == 0:
                        break
                    time.sleep(0.2)

                yield device
            finally:
                # qemu-nbd doesn't wait until the device is released. nbd-client does
                subprocess.run(["qemu-nbd", "--disconnect", device], check=True, stdout=subprocess.DEVNULL)
                subprocess.run(["nbd-client", "--disconnect", device], check=False, stdout=subprocess.DEVNULL)
            break
    else:
        raise RuntimeError("no free network block device")
