
import contextlib
import glob
import hashlib
import json
import os
import subprocess
import tempfile
import uuid

from . import osbuildtest


class TestAssemblers(osbuildtest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        subprocess.run(["modprobe", "nbd"], check=True)

    def run_assembler(self, name, options):
        with open("test/pipelines/f30-base.json") as f:
            base = json.load(f)
        pipeline = dict(base, assembler={ "name": name, "options": options })
        return self.run_osbuild("-", json.dumps(pipeline))

    def assertImageFile(self, filename, fmt, expected_size=None):
        info = json.loads(subprocess.check_output(["qemu-img", "info", "--output", "json", filename]))
        self.assertEqual(info["format"], fmt)
        self.assertEqual(info["virtual-size"], expected_size)

    def assertFilesystem(self, device, uuid, fstype, tree_id):
        output = subprocess.check_output(["blkid", "--output", "export", device], encoding="utf-8")
        blkid = dict(line.split("=") for line in output.strip().split("\n"))
        self.assertEqual(blkid["UUID"], uuid)
        self.assertEqual(blkid["TYPE"],fstype)

        with mount(device) as target_tree:
            tree = f"{self.store}/refs/{tree_id}"
            diff = json.loads(subprocess.check_output(["./tree-diff", tree, target_tree]))
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

    def assertPartitionTable(self, device, label, uuid, n_partitions, boot_partition=None):
        sfdisk = json.loads(subprocess.check_output(["sfdisk", "--json", device]))
        ptable = sfdisk["partitiontable"]

        self.assertEqual(ptable["label"], label)
        self.assertEqual(ptable["id"][2:], uuid[:8])
        self.assertEqual(len(ptable["partitions"]), n_partitions)

        if boot_partition:
            bootable = [p.get("bootable", False) for p in ptable["partitions"]]
            self.assertEqual(bootable.count(True), 1)
            self.assertEqual(bootable.index(True) + 1, boot_partition)

    def test_rawfs(self):
        options = {
            "filename": "image.raw",
            "root_fs_uuid": str(uuid.uuid4()),
            "size": 2 * 1024 * 1024 * 1024
        }
        tree_id, output_id = self.run_assembler("org.osbuild.rawfs", options)
        image = f"{self.store}/refs/{output_id}/image.raw"
        self.assertImageFile(image, "raw", options["size"])
        self.assertFilesystem(image, options["root_fs_uuid"], "ext4", tree_id)

    def test_qemu(self):
        for fmt in ["raw", "raw.xz", "qcow2", "vmdk", "vdi"]:
            with self.subTest(fmt=fmt):
                print(f"  {fmt}", flush=True)
                options = {
                    "format": fmt,
                    "filename": f"image.{fmt}",
                    "ptuuid": str(uuid.uuid4()),
                    "root_fs_uuid": str(uuid.uuid4()),
                    "size": 2 * 1024 * 1024 * 1024
                }
                tree_id, output_id = self.run_assembler("org.osbuild.qemu", options)
                image = f"{self.store}/refs/{output_id}/image.{fmt}"
                if fmt == "raw.xz":
                    subprocess.run(["unxz", image], check=True)
                    image = image[:-3]
                    fmt = "raw"
                self.assertImageFile(image, fmt, options["size"])
                with nbd_connect(image) as device:
                    self.assertPartitionTable(device, "dos", options["ptuuid"], 1, boot_partition=1)
                    self.assertGRUB2(device,
                                     "26e3327c6b5ac9b5e21d8b86f19ff7cb4d12fb2d0406713f936997d9d89de3ee",
                                     "1ebb35399388ba4007cee817a066570db948c450da911a3db67dba8083be247d",
                                     1024 * 1024)
                    self.assertFilesystem(device + "p1", options["root_fs_uuid"], "ext4", tree_id)

    def test_tar(self):
        cases = [
            ("tree.tar.gz", None, ["application/x-tar"]),
            ("tree.tar.gz", "gzip", ["application/x-gzip", "application/gzip"])
        ]
        for filename, compression, expected_mimetypes in cases:
            options = {
                    "filename": filename,
                    "compression": compression
            }
            tree_id, output_id = self.run_assembler("org.osbuild.tar", options)
            image = f"{self.store}/refs/{output_id}/{filename}"
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
                yield device
            finally:
                subprocess.run(["qemu-nbd", "--disconnect", device], check=True, stdout=subprocess.DEVNULL)
            break
    else:
        raise RuntimeError("no free network block device")
