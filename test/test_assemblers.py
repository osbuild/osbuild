
import contextlib
import json
import os
import subprocess
import tempfile
import uuid

from . import osbuildtest


class TestAssemblers(osbuildtest.TestCase):
    def test_rawfs(self):
        with open("test/pipelines/f30-base.json") as f:
            base = json.load(f)

        options = {
            "filename": "image.raw",
            "root_fs_uuid": str(uuid.uuid4()),
            "size": 2 * 1024 * 1024 * 1024
        }

        pipeline = dict(base, assembler = {
            "name": "org.osbuild.rawfs",
            "options": options
        })
        tree_id, output_id = self.run_osbuild("-", json.dumps(pipeline))

        image = f"{self.store}/refs/{output_id}/image.raw"

        self.assertEqual(os.path.getsize(image), options["size"])

        output = subprocess.check_output(["blkid", "--output", "export", image], encoding="utf-8")
        blkid = dict(line.split("=") for line in output.strip().split("\n"))
        self.assertEqual(blkid["UUID"], options["root_fs_uuid"])
        self.assertEqual(blkid["TYPE"], "ext4")

        with mount(image) as target_tree:
            tree = f"{self.store}/refs/{tree_id}"
            diff = json.loads(subprocess.check_output(["./tree-diff", tree, target_tree]))
            self.assertEqual(diff["added_files"], ["/lost+found"])
            self.assertEqual(diff["deleted_files"], [])
            self.assertEqual(diff["differences"], {})


@contextlib.contextmanager
def mount(device):
    with tempfile.TemporaryDirectory() as mountpoint:
        subprocess.run(["mount", "-o", "ro", device, mountpoint], check=True)
        try:
            yield mountpoint
        finally:
            subprocess.run(["umount", "--lazy", mountpoint], check=True)
