#
# Tests for the 'osbuild.util.checksum' module.
#

# pylint: disable=line-too-long

import tempfile
import unittest

from osbuild.util import checksum

CHECK_STRING = b"Checksum\nThis file\nConsistently."
CHECKSUMS = {
        "md5": "37eda131b189bede2816cc72dabf0252",
        "sha1": "6017eb45d9a006906ff81b7eb7d98ecdc92e1b20",
        "sha256": "e72fa48e1718534259f05303de0b28184718d229675ffa6314bb481991a90faa",
        "sha384": "35e3dcc878856d7f0bd12eb46781081682dd5a9da2af749dcfb3ff5d12c8fa323cd34a3d55c24b6d7cba4ae9a7203fb4",
        "sha512": "5d362859cea5393e3655eb93c743580cf6b466afaec8016bcd3fbaae07253e524135859292dce967d9d13bd5e3c24f1d095a9f5a3f4bc9ea923325d4fd688c64"
}

class TestChecksum(unittest.TestCase):
    def test_verify_checksum(self):
        with tempfile.NamedTemporaryFile(prefix="test.verify_checksum.") as f:
            f.write(CHECK_STRING)
            f.flush()

            for a, c in CHECKSUMS.items():
                self.assertTrue(checksum.verify_checksum(f.name, f"{a}:{c}"), a)
