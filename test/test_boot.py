
import subprocess
import unittest
from . import osbuildtest


class TestBoot(osbuildtest.TestCase):
    def test_boot(self):
        print("Building Fedora 30 image for boot test.")
        _, output_id = self.run_osbuild("test/pipelines/f30-boot.json")

        # Set up a boolean for test results.
        boot_successful = False

        # Set up a command to boot the image via qemu.
        qemu_boot_command = [
            "qemu-system-x86_64",
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
        ]

        # Run qemu.
        print("Booting image via qemu.")
        r = subprocess.Popen(
            qemu_boot_command,
            encoding="utf-8",
            stdout=subprocess.PIPE
        )

        # Monitor the qemu output for the "running" string which shows when
        # the instance has fully booted.
        print("Waiting for instance to fully boot.")
        for line in iter(r.stdout.readline, ''):
            # If the VM writes "running" to the console, everything worked!
            if "running" in line:
                print("Instance has fully booted!")
                boot_successful = True
                break

        # Stop qemu if it is still running.
        r.terminate()

        self.assertTrue(boot_successful)
