#
# Runtime / Integration Tests for ostree pipelines
#

import os
import tempfile
import unittest

from .. import test


@unittest.skipUnless(test.TestBase.have_test_data(), "no test-data access")
@unittest.skipUnless(test.TestBase.can_bind_mount(), "root-only")
class TestBoot(test.TestBase):
    def setUp(self):
        self.osbuild = test.OSBuild(self)

    def test_ostree_container_updates(self):
        #
        # Build a container.
        #

        manifest = os.path.join(self.locate_test_data(),
                                "manifests/fedora-ostree-container.json")

        with self.osbuild as osb:
            exports = ["container"]
            with tempfile.TemporaryDirectory(dir="/var/tmp") as temp_dir:
                osb.compile_file(manifest, output_dir=temp_dir, exports=exports)

                oci_archive = os.path.join(temp_dir, "container", "fedora-container.tar")
                self.assertTrue(os.path.exists(oci_archive))
