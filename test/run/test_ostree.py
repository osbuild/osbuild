#
# Runtime / Integration Tests for ostree pipelines
#

import os
import tempfile
import unittest

from .. import test


@unittest.skipUnless(test.TestBase.have_test_data(), "no test-data access")
@unittest.skipUnless(test.TestBase.can_bind_mount(), "root-only")
class TestOSTree(test.TestBase):
    def setUp(self):
        self.osbuild = test.OSBuild(self)

    def test_ostree(self):
        with self.osbuild as osb:
            with tempfile.TemporaryDirectory(dir="/var/tmp") as temp_dir:

                # Build a container
                manifest = os.path.join(self.locate_test_data(),
                                        "manifests/fedora-ostree-container.json")
                osb.compile_file(manifest,
                                 output_dir=temp_dir,
                                 checkpoints=["build", "ostree-tree", "ostree-commit"],
                                 exports=["container"])

                oci_archive = os.path.join(temp_dir, "container", "fedora-container.tar")
                self.assertTrue(os.path.exists(oci_archive))

                # build a bootable ISO
                manifest = os.path.join(self.locate_test_data(),
                                        "manifests/fedora-ostree-bootiso.json")
                osb.compile_file(manifest,
                                 output_dir=temp_dir,
                                 checkpoints=["build", "ostree-tree", "ostree-commit"],
                                 exports=["bootiso"])

                bootiso = os.path.join(temp_dir, "bootiso", "fedora-ostree-boot.iso")
                self.assertTrue(os.path.exists(bootiso))

                # build a qemu image
                manifest = os.path.join(self.locate_test_data(),
                                        "manifests/fedora-ostree-image.json")
                osb.compile_file(manifest,
                                 output_dir=temp_dir,
                                 checkpoints=["build", "ostree-tree", "ostree-commit"],
                                 exports=["qcow2"])

                bootiso = os.path.join(temp_dir, "qcow2", "disk.qcow2")
                self.assertTrue(os.path.exists(bootiso))
