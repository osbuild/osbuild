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
from osbuild.monitor import LogMonitor
from osbuild.pipeline import detect_host_runner
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

    def begin(self, pipeline: osbuild.Pipeline):
        self.counter["begin"] += 1

    def finish(self, result):
        self.counter["finish"] += 1
        self.output = self.logger.getvalue()

    def stage(self, stage: osbuild.Stage):
        self.counter["stages"] += 1
        self.stages.add(stage.id)

    def assembler(self, assembler: osbuild.Assembler):
        self.counter["assembler"] += 1
        self.asm = assembler.id

    def result(self, result: osbuild.pipeline.BuildResult):
        self.counter["result"] += 1
        self.results.add(result.id)

    def log(self, message: str):
        self.counter["log"] += 1
        self.logger.write(message)


class TestMonitor(unittest.TestCase):
    @unittest.skipUnless(test.TestBase.can_bind_mount(), "root-only")
    def test_log_monitor_vfuncs(self):
        # Checks the basic functioning of the LogMonitor
        runner = detect_host_runner()
        pipeline = osbuild.Pipeline(runner=runner)
        pipeline.add_stage("org.osbuild.noop", {}, {
            "isthisthereallife": False
        })
        pipeline.set_assembler("org.osbuild.noop")

        with tempfile.TemporaryDirectory() as tmpdir:
            storedir = os.path.join(tmpdir, "store")
            outputdir = os.path.join(tmpdir, "output")

            logfile = os.path.join(tmpdir, "log.txt")

            with open(logfile, "w") as log:
                monitor = LogMonitor(log.fileno())
                res = pipeline.run(storedir,
                                   monitor,
                                   libdir=os.path.abspath(os.curdir),
                                   output_directory=outputdir)

                with open(logfile) as f:
                    log = f.read()

            assert res
            self.assertIn(pipeline.stages[0].id, log)
            self.assertIn(pipeline.assembler.id, log)
            self.assertIn("isthisthereallife", log)

    @unittest.skipUnless(test.TestBase.can_bind_mount(), "root-only")
    def test_monitor_integration(self):
        # Checks the monitoring API is called properly from the pipeline
        runner = detect_host_runner()
        pipeline = osbuild.Pipeline(runner=runner)
        pipeline.add_stage("org.osbuild.noop", {}, {
            "isthisthereallife": False
        })
        pipeline.add_stage("org.osbuild.noop", {}, {
            "isthisjustfantasy": True
        })
        pipeline.set_assembler("org.osbuild.noop")

        with tempfile.TemporaryDirectory() as tmpdir:
            storedir = os.path.join(tmpdir, "store")
            outputdir = os.path.join(tmpdir, "output")

            tape = TapeMonitor()
            res = pipeline.run(storedir,
                               tape,
                               libdir=os.path.abspath(os.curdir),
                               output_directory=outputdir)

        assert res
        self.assertEqual(tape.counter["begin"], 1)
        self.assertEqual(tape.counter["finish"], 1)
        self.assertEqual(tape.counter["stages"], 2)
        self.assertEqual(tape.counter["assembler"], 1)
        self.assertEqual(tape.counter["stages"], 2)
        self.assertEqual(tape.counter["result"], 3)
        self.assertIn(pipeline.stages[0].id, tape.stages)
        self.assertIn(pipeline.assembler.id, tape.asm)
        self.assertIn("isthisthereallife", tape.output)
        self.assertIn("isthisjustfantasy", tape.output)
