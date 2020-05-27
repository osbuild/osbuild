#
# Runtime Tests for Bootable Pipelines
#

import os
import subprocess
import tempfile
import unittest

from .. import test


@unittest.skipUnless(test.TestBase.have_test_data(), "no test-data access")
class TestBoot(test.TestBase):
    def setUp(self):
        self.osbuild = test.OSBuild(self)

    def test_boot(self):
        #
        # Build an image and test-boot it.
        #

        manifest = os.path.join(self.locate_test_data(),
                                "manifests/fedora-boot.json")

        with self.osbuild as osb:
            osb.compile_file(manifest)
            with osb.map_output("fedora-boot.qcow2") as qcow2, \
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
