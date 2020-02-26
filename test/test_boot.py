
import subprocess
import unittest
from . import osbuildtest


class TestBoot(osbuildtest.TestCase):
    def test_boot(self):
        _, output_id = self.run_osbuild("test/pipelines/f30-boot.json")

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

            f"{self.get_path_to_store(output_id)}/f30-boot.qcow2"
        ], encoding="utf-8", stdout=subprocess.PIPE, check=True)

        self.assertEqual(r.stdout.strip(), "running")
