#
# Runtime Tests for the `osbuild` executable
#

import json
import subprocess
import unittest

from .. import test


class TestExecutable(unittest.TestCase):
    def setUp(self):
        self.osbuild = test.OSBuild(self)

    def test_invalid_manifest(self):
        invalid = json.dumps({"foo": 42})

        with self.osbuild as osb, self.assertRaises(subprocess.CalledProcessError) as e:
            osb.compile(invalid, check=True)

        self.assertEqual(e.exception.returncode, 2)

    def test_invalid_checkpoint(self):
        manifest = json.dumps({})

        with self.osbuild as osb, self.assertRaises(subprocess.CalledProcessError) as e:
            osb.compile(manifest, checkpoints=["f44f76973fb92446a2a33bfdb401361a47f70497"], check=True)

        self.assertEqual(e.exception.returncode, 1)
