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
from osbuild.monitor import LogMonitor
from osbuild.monitor import JSONSeqMonitor, Context, Progress, log_entry
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
    assert ctx.id == "e6305b7e8ccbc39ec88415ea955b89149faf6f51fb6c89831658068bc6850411"

    ctx_dict = ctx.as_dict()
    # should be a full dict
    assert "origin" in ctx_dict
    assert ctx_dict["id"] == "e6305b7e8ccbc39ec88415ea955b89149faf6f51fb6c89831658068bc6850411"
    assert "pipeline" in ctx_dict
    assert ctx_dict["pipeline"]["name"] == "test-pipeline"
    assert ctx_dict["pipeline"]["stage"]["name"] == "org.osbuild.noop"

    ctx_dict = ctx.as_dict()
    # should only have id
    assert ctx_dict["id"] == "e6305b7e8ccbc39ec88415ea955b89149faf6f51fb6c89831658068bc6850411"
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
    assert ctx_dict["id"] == "e6305b7e8ccbc39ec88415ea955b89149faf6f51fb6c89831658068bc6850411"
    assert len(ctx_dict) == 1


def test_progress():
    prog = Progress("test", total=12, unit="tests")
    subprog = Progress("test-sub1", total=3)
    prog.sub_progress(subprog)
    assert prog.done is None  # starts with None until the first incr()
    prog.incr()

    prog.incr(depth=1)
    progdict = prog.as_dict()
    assert progdict["done"] == 0
    assert progdict["progress"]["done"] == 0

    prog.incr(depth=1)
    progdict = prog.as_dict()
    assert progdict["done"] == 0
    assert progdict["progress"]["done"] == 1

    prog.incr()
    progdict = prog.as_dict()
    assert progdict["done"] == 1
    assert progdict["progress"]["done"] is None, "sub-progress did not reset"


def test_json_progress_monitor():
    index = osbuild.meta.Index(os.curdir)
    info = index.get_module_info("Stage", "org.osbuild.noop")

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
        mon.begin(manifest.pipelines["test-pipeline-second"])
        mon.log("pipeline 2 starting", origin="org.osbuild")
        mon.log("pipeline 2 message 2")

        tf.seek(0)
        log = tf.read().decode().strip().split(u"\x1e")

        assert len(log) == 7
        logitem = json.loads(log[0])
        assert logitem["message"] == "test-message-1"
        assert logitem["context"]["origin"] == "org.osbuild"

        logitem = json.loads(log[1])
        assert logitem["message"] == "test-message-2"
        assert logitem["context"]["origin"] == "test.origin.override"

        logitem = json.loads(log[2])
        assert logitem["message"] == "pipeline 1 message 1"
        assert logitem["context"]["origin"] == "org.osbuild"
        assert logitem["context"]["pipeline"]["name"] == "test-pipeline-first"
        # empty items are omited
        assert "name" not in logitem["context"]["pipeline"]["stage"]

        logitem = json.loads(log[3])
        assert logitem["message"] == "pipeline 1 message 2"
        assert logitem["context"]["origin"] == "org.osbuild"
        assert logitem["context"]["pipeline"]["name"] == "test-pipeline-first"
        assert logitem["context"]["pipeline"]["stage"]["name"] == "org.osbuild.noop"

        logitem = json.loads(log[4])
        assert logitem["message"] == "pipeline 1 finished"
        assert "origin" not in logitem["context"]
        assert len(logitem["context"]) == 1

        logitem = json.loads(log[5])
        assert logitem["message"] == "pipeline 2 starting"
        assert logitem["context"]["origin"] == "org.osbuild"
        assert logitem["context"]["pipeline"]["name"] == "test-pipeline-second"


def test_log_line_empty_is_fine():
    empty = log_entry()
    assert len(empty) == 1
    assert empty["timestamp"] > time.time()-60
    assert empty["timestamp"] < time.time()+60


def test_log_line_with_entries():
    ctx = Context("some-origin")
    progress = Progress(name="foo", total=2)
    entry = log_entry("some-msg", ctx, progress)
    assert len(entry) == 4
    assert entry["message"] == "some-msg"
    assert isinstance(entry["context"], dict)
    assert isinstance(entry["progress"], dict)
    assert entry["timestamp"] > 0
