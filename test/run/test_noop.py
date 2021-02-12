#
# Runtime Tests for No-op Pipelines
#

import json
import unittest
import tempfile

from .. import test


NOOP_V2 = {
    "version": "2",
    "pipelines": [
        {
            "name": "noop",
            "stages": [
                {
                    "type": "org.osbuild.noop",
                    "options": {"zero": 0},
                    "inputs": {
                        "tree": {
                            "type": "org.osbuild.noop",
                            "origin": "org.osbuild.pipeline",
                            "references": {
                                "foo": {}
                            }
                        }
                    }
                }
            ]
        }
    ]
}

class TestNoop(unittest.TestCase):
    def setUp(self):
        self.osbuild = test.OSBuild(self)

    def test_noop(self):
        #
        # Run a noop Pipeline. Run twice to verify the cache does not affect
        # the operation (we do not have checkpoints, nor any stages that could
        # be checkpointed).
        #
        # Then run the entire thing again, to verify our own `osbuild` executor
        # tears things down properly and allows to be executed multiple times.
        #

        with self.osbuild as osb:
            osb.compile("{}")
            osb.compile("{}")

        with self.osbuild as osb:
            osb.compile("{}")
            osb.compile("{}")


    def test_noop_v2(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.osbuild as osb:
                osb.compile(json.dumps(NOOP_V2), output_dir=tmp)
