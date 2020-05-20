#
# Runtime Tests for No-op Pipelines
#

import unittest

from .. import test


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
