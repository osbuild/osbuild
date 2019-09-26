
import subprocess
import tempfile
import unittest
from . import osbuildtest


class TestBoot(osbuildtest.TestCase):
    def test_boot(self):
        with tempfile.TemporaryDirectory(dir="/var/tmp") as store:
            _, output_id = self.run_osbuild("test/pipelines/f30-boot.json", store=store)

            r = subprocess.run(["qemu-system-x86_64",
                "-snapshot",
                "-m", "1024",
                "-accel", "kvm:hvf:tcg",

                # be silent
                "-nographic",
                "-monitor", "none",
                "-serial", "none",

                # create /dev/vport0p1
                "-chardev", "stdio,id=stdio",
                "-device", "virtio-serial",
                "-device", "virtserialport,chardev=stdio",

                f"{store}/refs/{output_id}/f30-boot.qcow2"
            ], encoding="utf-8", capture_output=True, check=True)

            self.assertEqual(r.stdout.strip(), "running")
