import os
import subprocess
import unittest
from . import osbuildtest


class TestBoot(osbuildtest.TestCase):
    def test_boot(self):
        print("\n🏗️  Building Fedora 30 image for boot test.")
        _, output_id = self.run_osbuild("test/pipelines/f30-boot.json")

        # Set up a boolean for test results.
        boot_successful = False

        # Set up a command to boot the image via qemu.
        qemu_boot_command = [
            "qemu-system-x86_64",
            "-nographic",
            "-serial", "mon:stdio",
            f"{self.get_path_to_store(output_id)}/f30-boot.qcow2"
        ]

        # Run qemu.
        print("🤹‍♂️  Booting image via qemu.")
        p = subprocess.Popen(
            qemu_boot_command,
            encoding="utf-8",
            stdout=subprocess.PIPE
        )
        pid = p.pid

        # Monitor the qemu output to know when the instance has booted.
        print("🤔  Waiting for instance to fully boot.")
        for line in iter(p.stdout.readline, ''):
            if "Initializing machine ID from random generator" in line:
                print("🥳  Instance has fully booted!")
                boot_successful = True
                break

        # Stop qemu if it is still running.
        os.kill(pid, 0)
        p.kill()
        p.wait()
        p.terminate()

        self.assertTrue(boot_successful)
