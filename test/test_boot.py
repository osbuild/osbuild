
import os
import subprocess
import tempfile
import unittest

from . import test


class TestBoot(unittest.TestCase):
    def setUp(self):
        self.osbuild = test.OSBuild(self)

    def test_boot(self):
        #
        # Build an image and test-boot it.
        #

        with self.osbuild as osb:
            osb.compile_file("test/pipelines/f30-boot.json")
            with osb.map_output("f30-boot.qcow2") as qcow2, \
                 tempfile.TemporaryDirectory() as d:

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

                                qcow2],
                               encoding="utf-8",
                               check=True)
                with open(output_file, "r") as f:
                    self.assertEqual(f.read().strip(), "running")
