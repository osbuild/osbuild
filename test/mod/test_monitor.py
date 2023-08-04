#
# Test for monitoring classes and integration
#

import io
import os
import sys
import tempfile
import unittest
from collections import defaultdict

import osbuild
import osbuild.meta
from osbuild.manifest import Runner
from osbuild.monitor import LogMonitor
from osbuild.objectstore import ObjectStore

from .. import test


class TapeMonitor(osbuild.monitor.BaseMonitor):
    """Record the usage of all called functions"""

    def __init__(self):
        super().__init__(sys.stderr.fileno())
        self.counter = defaultdict(int)
        self.stages = set()
        self.asm = None
        self.results = set()
        self.logger = io.StringIO()
        self.output = None

    def begin(self, pipeline: osbuild.Pipeline):
        self.counter["begin"] += 1

    def finish(self, result):
        self.counter["finish"] += 1
        self.output = self.logger.getvalue()

    def stage(self, stage: osbuild.Stage):
        self.counter["stages"] += 1
        self.stages.add(stage.id)

    def result(self, result: osbuild.manifest.BuildResult):
        self.counter["result"] += 1
        self.results.add(result.id)

    def log(self, message: str):
        self.counter["log"] += 1
        self.logger.write(message)


class TestMonitor(unittest.TestCase):
    @unittest.skipUnless(test.TestBase.can_bind_mount(), "root-only")
    def test_log_monitor_vfuncs(self):
        # Checks the basic functioning of the LogMonitor
        index = osbuild.meta.Index(os.curdir)

        runner = Runner(index.detect_host_runner())
        pipeline = osbuild.Pipeline("pipeline", runner=runner)
        info = index.get_module_info("Stage", "org.osbuild.noop")
        pipeline.add_stage(info, {
            "isthisthereallife": False
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            storedir = os.path.join(tmpdir, "store")

            logfile = os.path.join(tmpdir, "log.txt")

            with open(logfile, "w", encoding="utf8") as log, ObjectStore(storedir) as store:
                monitor = LogMonitor(log.fileno())
                res = pipeline.run(store,
                                   monitor,
                                   libdir=os.path.abspath(os.curdir))

                with open(logfile, encoding="utf8") as f:
                    log = f.read()

            assert res
            self.assertIn(pipeline.stages[0].id, log)
            self.assertIn("isthisthereallife", log)

    @unittest.skipUnless(test.TestBase.can_bind_mount(), "root-only")
    def test_monitor_integration(self):
        # Checks the monitoring API is called properly from the pipeline
        index = osbuild.meta.Index(os.curdir)
        runner = Runner(index.detect_host_runner())

        pipeline = osbuild.Pipeline("pipeline", runner=runner)
        noop_info = index.get_module_info("Stage", "org.osbuild.noop")
        pipeline.add_stage(noop_info, {
            "isthisthereallife": False
        })
        pipeline.add_stage(noop_info, {
            "isthisjustfantasy": True
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            storedir = os.path.join(tmpdir, "store")

            tape = TapeMonitor()
            with ObjectStore(storedir) as store:
                res = pipeline.run(store,
                                   tape,
                                   libdir=os.path.abspath(os.curdir))

        assert res
        self.assertEqual(tape.counter["begin"], 1)
        self.assertEqual(tape.counter["finish"], 1)
        self.assertEqual(tape.counter["stages"], 2)
        self.assertEqual(tape.counter["stages"], 2)
        self.assertEqual(tape.counter["result"], 2)
        self.assertIn(pipeline.stages[0].id, tape.stages)
        self.assertIn("isthisthereallife", tape.output)
        self.assertIn("isthisjustfantasy", tape.output)
