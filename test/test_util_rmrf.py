#
# Tests for the `osbuild.util.rmrf` module.
#


import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

import osbuild.util.rmrf as rmrf


def can_set_immutable():
    with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
        try:
            os.makedirs(f"{tmp}/f")
            # fist they give it ...
            subprocess.run(["chattr", "+i", f"{tmp}/f"], check=True)
            # ... then they take it away
            subprocess.run(["chattr", "-i", f"{tmp}/f"], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
        return True


class TestUtilLinux(unittest.TestCase):
    @unittest.skipUnless(can_set_immutable(), "Need root permissions")
    def test_rmtree_immutable(self):
        #
        # Test the `rmrf.rmtree()` helper and verify it can correctly unlink
        # files that are marked immutable.
        #

        with tempfile.TemporaryDirectory(dir="/var/tmp") as vartmpdir:
            os.makedirs(f"{vartmpdir}/dir")

            p = pathlib.Path(f"{vartmpdir}/dir/immutable")
            p.touch()
            subprocess.run(["chattr", "+i", f"{vartmpdir}/dir/immutable"],
                           check=True)

            with self.assertRaises(PermissionError):
                shutil.rmtree(f"{vartmpdir}/dir")

            rmrf.rmtree(f"{vartmpdir}/dir")


if __name__ == "__main__":
    unittest.main()
