#
# Tests for the `osbuild.util.rmrf` module.
#

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from osbuild.util import rmrf

from .. import test


class TestUtilLinux(unittest.TestCase):
    @unittest.skipUnless(test.TestBase.can_modify_immutable("/var/tmp"), "root-only")
    def test_rmtree_immutable(self):
        #
        # Test the `rmrf.rmtree()` helper and verify it can correctly unlink
        # files that are marked immutable.
        #

        with tempfile.TemporaryDirectory(dir="/var/tmp") as vartmpdir:
            os.makedirs(f"{vartmpdir}/dir")

            p = pathlib.Path(f"{vartmpdir}/dir/immutable")
            p.touch()
            subprocess.run(["chattr", "+i", f"{vartmpdir}/dir/immutable"], check=True)

            with self.assertRaises(PermissionError):
                shutil.rmtree(f"{vartmpdir}/dir")

            rmrf.rmtree(f"{vartmpdir}/dir")
