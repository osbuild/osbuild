
import os
import subprocess
import tempfile

from . import osbuildtest


class TestBoot(osbuildtest.TestCase):
    def test_boot(self):
        _, output_id = self.run_osbuild("test/pipelines/f30-boot.json")

        with tempfile.TemporaryDirectory() as d:
            output_file = os.path.join(d, "output")

            subprocess.run(["qemu-system-x86_64",
                            "-snapshot",
                            "-m", "1024",
                            "-M", "accel=kvm:hvf:tcg",

                            # be silent
                            "-nographic",
                            "-monitor", "none",
                            "-serial", "none",

                            # create /dev/vport0p1
                            "-chardev", f"file,path={output_file},id=stdio",
                            "-device", "virtio-serial",
                            "-device", "virtserialport,chardev=stdio",

                            f"{self.get_path_to_store(output_id)}/f30-boot.qcow2"],
                           encoding="utf-8",
                           check=True)

            with open(output_file, "r") as f:
                self.assertEqual(f.read().strip(), "running")
