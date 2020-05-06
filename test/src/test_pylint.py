#
# Run `pylint` on all python sources.
#

import subprocess
import unittest

from .. import test


@unittest.skipUnless(test.TestBase.have_test_checkout(), "no test-checkout access")
class TestPylint(test.TestBase, unittest.TestCase):
    def test_pylint(self):
        #
        # Run `pylint` on all python sources. We simply use `find` to locate
        # all `*.py` files, and then manually select the reverse-domain named
        # modules we have.
        #

        path = self.locate_test_checkout()
        options = "--errors-only"

        subprocess.run(f"find {path} -type f -name '*.py' | xargs pylint {options}",
                       shell=True, check=True)
        subprocess.run(f"pylint {options}"
                       + f" {path}/assemblers/*"
                       + f" {path}/runners/*"
                       + f" {path}/sources/*"
                       + f" {path}/stages/*",
                       shell=True, check=True)
