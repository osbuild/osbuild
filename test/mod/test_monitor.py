#
# Test for monitoring classes and integration
#

import io
import json
import os
import sys
import tempfile
import time
import unittest
from collections import defaultdict

import osbuild
import osbuild.meta
from osbuild.monitor import Context, JSONSeqMonitor, LogMonitor, Progress, log_entry
from osbuild.objectstore import ObjectStore
from osbuild.pipeline import Runner

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

    def finish(self, results):
        self.counter["finish"] += 1
        self.output = self.logger.getvalue()

    def stage(self, stage: osbuild.Stage):
        self.counter["stages"] += 1
        self.stages.add(stage.id)

    def result(self, result: osbuild.pipeline.BuildResult):
        self.counter["result"] += 1
        self.results.add(result.id)

    def log(self, message: str, origin: str = None):
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


def test_context():
    index = osbuild.meta.Index(os.curdir)

    runner = Runner(index.detect_host_runner())
    pipeline = osbuild.Pipeline(name="test-pipeline", runner=runner)
    index = osbuild.meta.Index(os.curdir)
    info = index.get_module_info("Stage", "org.osbuild.noop")
    stage = osbuild.Stage(info, {}, None, None, {}, None)
    ctx = Context("org.osbuild.test", pipeline, stage)
    assert ctx.id == "75bf3feab3d5662744c3ac38406ba73142aeb67666b1180bc1006f913b18f792"

    ctx_dict = ctx.as_dict()
    # should be a full dict
    assert "origin" in ctx_dict
    assert ctx_dict["id"] == "75bf3feab3d5662744c3ac38406ba73142aeb67666b1180bc1006f913b18f792"
    assert "pipeline" in ctx_dict
    assert ctx_dict["pipeline"]["name"] == "test-pipeline"
    assert ctx_dict["pipeline"]["stage"]["name"] == "org.osbuild.noop"

    ctx_dict = ctx.as_dict()
    # should only have id
    assert ctx_dict["id"] == "75bf3feab3d5662744c3ac38406ba73142aeb67666b1180bc1006f913b18f792"
    assert len(ctx_dict) == 1

    ctx.origin = "org.osbuild.test-2"
    ctx_dict = ctx.as_dict()
    # should be a full dict again
    assert "origin" in ctx_dict
    assert "pipeline" in ctx_dict
    assert ctx_dict["pipeline"]["name"] == "test-pipeline"
    assert ctx_dict["pipeline"]["stage"]["name"] == "org.osbuild.noop"

    ctx.origin = "org.osbuild.test"
    ctx_dict = ctx.as_dict()
    # should only have id again (old context ID)
    assert ctx_dict["id"] == "75bf3feab3d5662744c3ac38406ba73142aeb67666b1180bc1006f913b18f792"
    assert len(ctx_dict) == 1


def test_progress():
    prog = Progress("test", total=12)
    prog.sub_progress = Progress("test-sub1", total=3)
    # we start empty
    progdict = prog.as_dict()
    assert progdict["done"] == 0
    assert progdict["progress"]["done"] == 0

    # incr a sub_progress only affect sub_progress
    prog.sub_progress.incr()
    progdict = prog.as_dict()
    assert progdict["done"] == 0
    assert progdict["progress"]["done"] == 1

    prog.sub_progress.incr()
    progdict = prog.as_dict()
    assert progdict["done"] == 0
    assert progdict["progress"]["done"] == 2

    prog.incr()
    progdict = prog.as_dict()
    assert progdict["done"] == 1
    assert progdict.get("progress") is None, "sub-progress did not reset"


# pylint: disable=too-many-statements
def test_json_progress_monitor():
    index = osbuild.meta.Index(os.curdir)
    info = index.get_module_info("Stage", "org.osbuild.noop")
    fake_noop_stage = osbuild.pipeline.Stage(info, None, None, None, None, None)

    manifest = osbuild.Manifest()
    pl1 = manifest.add_pipeline("test-pipeline-first", "", "")
    first_stage = pl1.add_stage(info, {})
    pl1.add_stage(info, {})

    pl2 = manifest.add_pipeline("test-pipeline-second", "", "")
    pl2.add_stage(info, {})
    pl2.add_stage(info, {})
    manifest.add_pipeline(pl2, "", "")

    with tempfile.TemporaryFile() as tf:
        mon = JSONSeqMonitor(tf.fileno(), manifest)
        mon.log("test-message-1")
        mon.log("test-message-2", origin="test.origin.override")
        mon.begin(manifest.pipelines["test-pipeline-first"])
        mon.log("pipeline 1 message 1")
        mon.stage(first_stage)
        mon.log("pipeline 1 message 2")
        mon.log("pipeline 1 finished", origin="org.osbuild")
        mon.result(osbuild.pipeline.BuildResult(
            fake_noop_stage, returncode=0, output="output", error=None))
        mon.finish({"success": True, "name": "test-pipeline-first"})
        mon.begin(manifest.pipelines["test-pipeline-second"])
        mon.log("pipeline 2 starting", origin="org.osbuild")
        mon.log("pipeline 2 message 2")

        tf.seek(0)
        log = tf.read().decode().strip().split("\x1e")

        expected_total = 12
        assert len(log) == expected_total
        i = 0
        logitem = json.loads(log[i])
        assert logitem["message"] == "test-message-1"
        assert logitem["context"]["origin"] == "org.osbuild"
        i += 1

        logitem = json.loads(log[i])
        assert logitem["message"] == "test-message-2"
        assert logitem["context"]["origin"] == "test.origin.override"
        i += 1

        logitem = json.loads(log[i])
        assert logitem["message"] == "Starting pipeline test-pipeline-first"
        assert logitem["context"]["pipeline"]["name"] == "test-pipeline-first"
        # empty items are omited
        assert "name" not in logitem["context"]["pipeline"]["stage"]
        i += 1

        logitem = json.loads(log[i])
        assert logitem["message"] == "pipeline 1 message 1"
        assert logitem["context"]["origin"] == "org.osbuild"
        assert logitem["context"]["pipeline"]["name"] == "test-pipeline-first"
        i += 1

        logitem = json.loads(log[i])
        assert logitem["message"] == "Starting module org.osbuild.noop"
        assert logitem["context"]["origin"] == "osbuild.monitor"
        assert logitem["context"]["pipeline"]["name"] == "test-pipeline-first"
        assert logitem["context"]["pipeline"]["stage"]["name"] == "org.osbuild.noop"
        id_start_module = logitem["context"]["id"]
        i += 1

        logitem = json.loads(log[i])
        assert logitem["message"] == "pipeline 1 message 2"
        assert logitem["context"]["origin"] == "org.osbuild"
        assert logitem["context"]["pipeline"]["name"] == "test-pipeline-first"
        i += 1

        logitem = json.loads(log[i])
        assert logitem["message"] == "pipeline 1 finished"
        prev_ctx_id = json.loads(log[i - 1])["context"]["id"]
        assert logitem["context"]["id"] == prev_ctx_id
        assert len(logitem["context"]) == 1
        i += 1

        logitem = json.loads(log[i])
        assert logitem["message"] == "Finished module org.osbuild.noop"
        assert logitem["context"]["id"] == id_start_module
        i += 1

        logitem = json.loads(log[i])
        assert logitem["message"] == "Finished pipeline test-pipeline-first"
        assert logitem["context"]["id"] == id_start_module
        i += 1

        logitem = json.loads(log[i])
        assert logitem["message"] == "Starting pipeline test-pipeline-second"
        assert logitem["context"]["origin"] == "osbuild.monitor"
        assert logitem["context"]["pipeline"]["name"] == "test-pipeline-second"
        i += 1

        logitem = json.loads(log[i])
        assert logitem["message"] == "pipeline 2 starting"
        assert logitem["context"]["origin"] == "org.osbuild"
        assert logitem["context"]["pipeline"]["name"] == "test-pipeline-second"
        i += 1

        logitem = json.loads(log[i])
        assert logitem["message"] == "pipeline 2 message 2"
        prev_ctx_id = json.loads(log[i - 1])["context"]["id"]
        assert logitem["context"]["id"] == prev_ctx_id
        i += 1

        assert i == expected_total


def test_log_line_empty_is_fine():
    empty = log_entry()
    assert len(empty) == 1
    assert empty["timestamp"] > time.time() - 60
    assert empty["timestamp"] < time.time() + 60


def test_log_line_with_entries():
    ctx = Context("some-origin")
    progress = Progress(name="foo", total=2)
    entry = log_entry("some-msg", ctx, progress)
    assert len(entry) == 4
    assert entry["message"] == "some-msg"
    assert isinstance(entry["context"], dict)
    assert isinstance(entry["progress"], dict)
    assert entry["timestamp"] > 0


def test_context_id():
    ctx = Context()
    assert ctx.id == "20bf38c0723b15c2c9a52733c99814c298628526d8b8eabf7c378101cc9a9cf3"
    ctx._origin = "foo"  # pylint: disable=protected-access
    assert ctx.id != "00d202e4fc9d917def414d1c9f284b137287144087ec275f2d146d9d47b3c8bb"
