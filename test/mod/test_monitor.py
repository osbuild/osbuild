#
# Test for monitoring classes and integration
#

import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from collections import defaultdict
from unittest.mock import Mock, patch

import pytest

import osbuild
import osbuild.meta
from osbuild.monitor import (
    RICH_AVAILABLE,
    Context,
    JSONSeqMonitor,
    LogMonitor,
    Progress,
    log_entry,
)

try:
    from osbuild.monitor import PrettyMonitor
except ImportError:
    PrettyMonitor = None
from osbuild.objectstore import ObjectStore
from osbuild.pipeline import BuildResult, Runner, Stage

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

    @unittest.skipUnless(RICH_AVAILABLE and PrettyMonitor, "rich not available")
    @unittest.skipUnless(test.TestBase.can_bind_mount(), "root-only")
    @patch('osbuild.monitor.Console')
    @patch('osbuild.monitor.RichProgress')
    def test_pretty_monitor_vfuncs(self, mock_rich_progress, mock_console):
        # Test the basic functioning of the PrettyMonitor with mocked Rich components
        index = osbuild.meta.Index(os.curdir)

        runner = Runner(index.detect_host_runner())
        pipeline = osbuild.Pipeline("pipeline", runner=runner)
        info = index.get_module_info("Stage", "org.osbuild.noop")
        pipeline.add_stage(info, {
            "prettytestkey": "prettytestvalue"
        })

        # Mock Rich components to avoid complex terminal interactions
        mock_progress_instance = Mock()
        mock_rich_progress.return_value = mock_progress_instance
        mock_console_instance = Mock()
        mock_console.return_value = mock_console_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            storedir = os.path.join(tmpdir, "store")

            logfile = os.path.join(tmpdir, "log.txt")

            with open(logfile, "w", encoding="utf8") as log, ObjectStore(storedir) as store:
                monitor = PrettyMonitor(log.fileno(), 1, 1)  # 1 pipeline, 1 stage
                res = pipeline.run(store,
                                   monitor,
                                   libdir=os.path.abspath(os.curdir))

            assert res
            # Verify that Rich components were initialized
            mock_console.assert_called_once()
            mock_rich_progress.assert_called_once()

            # Verify that the progress display was started and stopped
            mock_progress_instance.start.assert_called_once()
            mock_progress_instance.stop.assert_called_once()

            # Verify that progress was updated
            assert mock_progress_instance.update.call_count >= 1

    @unittest.skipUnless(RICH_AVAILABLE and PrettyMonitor, "rich not available")
    @unittest.skipUnless(test.TestBase.can_bind_mount(), "root-only")
    @patch('osbuild.monitor.Console')
    @patch('osbuild.monitor.RichProgress')
    def test_pretty_monitor_integration(self, mock_rich_progress, mock_console):
        # Test the PrettyMonitor integration with the pipeline system
        index = osbuild.meta.Index(os.curdir)
        runner = Runner(index.detect_host_runner())

        pipeline = osbuild.Pipeline("test-pipeline", runner=runner)
        noop_info = index.get_module_info("Stage", "org.osbuild.noop")
        pipeline.add_stage(noop_info, {
            "stage1": "test1"
        })
        pipeline.add_stage(noop_info, {
            "stage2": "test2"
        })

        # Mock Rich components
        mock_progress_instance = Mock()
        mock_rich_progress.return_value = mock_progress_instance
        mock_console_instance = Mock()
        mock_console.return_value = mock_console_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            storedir = os.path.join(tmpdir, "store")

            with open(os.devnull, "w", encoding="utf8") as devnull, ObjectStore(storedir) as store:
                monitor = PrettyMonitor(devnull.fileno(), 1, 2)  # 1 pipeline, 2 stages
                res = pipeline.run(store,
                                   monitor,
                                   libdir=os.path.abspath(os.curdir))

        assert res
        # Verify rich components were properly used
        mock_console.assert_called_once()
        mock_rich_progress.assert_called_once()

        # Verify progress lifecycle
        mock_progress_instance.start.assert_called_once()
        mock_progress_instance.stop.assert_called_once()

        # Should have created overall task and updated progress for each stage
        mock_progress_instance.add_task.assert_called_once()
        # At least one update call for each stage plus completion
        assert mock_progress_instance.update.call_count >= 2


@unittest.skipUnless(RICH_AVAILABLE and PrettyMonitor, "rich not available")
@patch('osbuild.monitor.Console')
@patch('osbuild.monitor.RichProgress')
def test_pretty_monitor_basic(mock_rich_progress, mock_console):
    """Test basic PrettyMonitor functionality without full pipeline integration"""
    # Mock Rich components
    mock_progress_instance = Mock()
    mock_rich_progress.return_value = mock_progress_instance
    mock_console_instance = Mock()
    mock_console.return_value = mock_console_instance

    # Create mock pipeline and stage
    mock_pipeline = Mock()
    mock_pipeline.name = "test-pipeline"
    mock_pipeline.id = "test123456789"
    mock_pipeline.stages = [Mock(), Mock()]  # Two stages

    mock_stage = Mock()
    mock_stage.name = "org.osbuild.test"
    mock_stage.id = "stage123"

    mock_result = Mock()
    mock_result.name = "org.osbuild.test"
    mock_result.success = True
    mock_result.output = "Test stage completed"

    with tempfile.NamedTemporaryFile() as tmp:
        # Test monitor initialization
        monitor = PrettyMonitor(tmp.fileno(), 1, 2)  # 1 pipeline, 2 stages

        # Test begin
        monitor.begin(mock_pipeline)
        mock_console.assert_called_once()
        mock_rich_progress.assert_called_once()
        mock_progress_instance.start.assert_called_once()
        mock_progress_instance.add_task.assert_called_once()

        # Test stage
        monitor.stage(mock_stage)
        assert monitor.current_stage == "org.osbuild.test"

        # Test result
        monitor.result(mock_result)

        # Test finish
        results = {"success": True, "name": "test-pipeline"}
        monitor.finish(results)
        mock_progress_instance.stop.assert_called_once()


@unittest.skipIf(RICH_AVAILABLE, "rich is available")
def test_pretty_monitor_requires_rich():
    """Test that PrettyMonitor fails gracefully when Rich is not available"""
    with tempfile.NamedTemporaryFile() as tmp:
        with pytest.raises(RuntimeError, match="PrettyMonitor requires python3-rich to be installed"):
            PrettyMonitor(tmp.fileno(), 1, 1)


def test_pretty_monitor_error_handling():
    """Test PrettyMonitor error message handling and display"""
    if not RICH_AVAILABLE or not PrettyMonitor:
        pytest.skip("Rich not available")

    with patch('osbuild.monitor.Console') as mock_console, \
            patch('osbuild.monitor.RichProgress') as mock_rich_progress:

        mock_progress_instance = Mock()
        mock_rich_progress.return_value = mock_progress_instance
        mock_console_instance = Mock()
        mock_console.return_value = mock_console_instance

        # Test error handling
        mock_pipeline = Mock()
        mock_pipeline.name = "error-test"
        mock_pipeline.id = "error123"
        mock_pipeline.stages = [Mock()]

        mock_stage = Mock()
        mock_stage.name = "org.osbuild.failing-stage"

        # Mock a failed result
        mock_failed_result = Mock()
        mock_failed_result.name = "org.osbuild.failing-stage"
        mock_failed_result.success = False
        mock_failed_result.output = "Error: Something went wrong"

        with tempfile.NamedTemporaryFile() as tmp:
            monitor = PrettyMonitor(tmp.fileno(), 1, 1)  # 1 pipeline, 1 stage
            monitor.begin(mock_pipeline)
            monitor.stage(mock_stage)
            monitor.result(mock_failed_result)

            # Verify error was tracked
            assert len(monitor.failed_stages) == 1

            # Log messages are now ignored (passed through), no filtering
            monitor.log("ERROR: This is an error message")
            monitor.log("WARNING: This is a warning")
            monitor.log("INFO: This is just info")

            # Failed stages should remain 1 (only from failed result, not from log messages)
            assert len(monitor.failed_stages) == 1


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
        mon = JSONSeqMonitor(tf.fileno(), len(manifest.sources) + len(manifest.pipelines))
        mon.log("test-message-1")
        mon.log("test-message-2", origin="test.origin.override")
        mon.begin(manifest.pipelines["test-pipeline-first"])
        mon.log("pipeline 1 message 1")
        mon.stage(first_stage)
        mon.log("pipeline 1 message 2")
        mon.log("pipeline 1 finished", origin="org.osbuild")
        mon.result(osbuild.pipeline.BuildResult(
            fake_noop_stage, returncode=0, output="some output", error=None))
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
        assert logitem["progress"]["progress"]["name"] == "pipeline: test-pipeline-first"
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
        assert logitem["result"] == {
            "id": fake_noop_stage.id,
            "name": "org.osbuild.noop",
            "output": "some output",
            "success": True,
        }
        i += 1

        logitem = json.loads(log[i])
        assert logitem["message"] == "Finished pipeline test-pipeline-first"
        assert logitem["context"]["id"] == id_start_module
        i += 1

        logitem = json.loads(log[i])
        assert logitem["message"] == "Starting pipeline test-pipeline-second"
        assert logitem["progress"]["progress"]["name"] == "pipeline: test-pipeline-second"
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


def test_monitor_download_happy(tmp_path):
    store = ObjectStore(tmp_path)
    tape = TapeMonitor()
    happy_source = Mock()

    manifest = osbuild.Manifest()
    manifest.sources = [happy_source]
    manifest.download(store, tape)
    assert tape.counter["begin"] == 1
    assert tape.counter["finish"] == 1
    assert tape.counter["result"] == 1
    # no stage was run as part of the download so this is nil
    assert tape.counter["stages"] == 0


def test_monitor_download_error(tmp_path):
    store = ObjectStore(tmp_path)
    tape = TapeMonitor()
    failing_source = Mock()
    failing_source.download.side_effect = osbuild.host.RemoteError("name", "value", "stack")

    manifest = osbuild.Manifest()
    manifest.sources = [failing_source]
    # this is different from stage failures, those do not raise exceptions
    with pytest.raises(osbuild.host.RemoteError):
        manifest.download(store, tape)
    assert tape.counter["begin"] == 1
    assert tape.counter["result"] == 1
    # this is different from stage failures that emit a "finish" on failure
    # here
    assert tape.counter["finish"] == 0


@patch.object(osbuild.sources.Source, "download")
def test_jsonseq_download_happy(_, tmp_path):
    store = ObjectStore(tmp_path)
    index = osbuild.meta.Index(os.curdir)
    info = index.get_module_info("Source", "org.osbuild.curl")
    happy_source = osbuild.sources.Source(info, {}, None)

    manifest = osbuild.Manifest()
    manifest.sources = [happy_source]
    with tempfile.TemporaryFile() as tf:
        mon = JSONSeqMonitor(tf.fileno(), 1)
        manifest.download(store, mon)

        tf.flush()
        tf.seek(0)
        log = []
        for line in tf.read().decode().strip().split("\x1e"):
            log.append(json.loads(line))
        assert len(log) == 3
        assert log[0]["message"] == "Starting pipeline source org.osbuild.curl"
        assert log[1]["message"] == "Finished module source org.osbuild.curl"
        assert log[1]["result"]["name"] == "source org.osbuild.curl"
        assert log[1]["result"]["success"]
        assert log[2]["message"] == "Finished pipeline org.osbuild.curl"


@patch.object(osbuild.sources.Source, "download")
def test_jsonseq_download_unhappy(mocked_download, tmp_path):
    store = ObjectStore(tmp_path)
    index = osbuild.meta.Index(os.curdir)
    info = index.get_module_info("Source", "org.osbuild.curl")
    failing_source = osbuild.sources.Source(info, {}, None)
    mocked_download.side_effect = osbuild.host.RemoteError("RuntimeError", "curl: error download ...", "error stack")

    manifest = osbuild.Manifest()
    manifest.sources = [failing_source]
    with tempfile.TemporaryFile() as tf:
        mon = JSONSeqMonitor(tf.fileno(), 1)
        with pytest.raises(osbuild.host.RemoteError):
            manifest.download(store, mon)

        tf.flush()
        tf.seek(0)
        log = []
        for line in tf.read().decode().strip().split("\x1e"):
            log.append(json.loads(line))
        assert len(log) == 2
        assert log[0]["message"] == "Starting pipeline source org.osbuild.curl"
        assert log[1]["message"] == "Finished module source org.osbuild.curl"
        assert log[1]["result"]["name"] == "source org.osbuild.curl"
        assert log[1]["result"]["success"] is False
        assert log[1]["result"]["output"] == "RuntimeError: curl: error download ...\n error stack"


def test_json_progress_monitor_handles_racy_writes(tmp_path):
    output_path = tmp_path / "jsonseq.log"
    with output_path.open("w") as fp:
        mon = JSONSeqMonitor(fp.fileno(), 10)

        def racy_write(s):
            for i in range(20):
                mon.log(f"{s}: {i}")
                time.sleep(0.0001)
        t1 = threading.Thread(target=racy_write, args=("msg from t1",))
        t2 = threading.Thread(target=racy_write, args=("msg from t2",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    # ensure the file is valid jsonseq
    with output_path.open() as fp:
        for line in fp.readlines():
            line = line.strip().strip("\1xe")
            try:
                json.loads(line)
            except json.decoder.JSONDecodeError:
                pytest.fail(f"the jsonseq stream is not valid json, got {line}")


def test_json_progress_monitor_excessive_output_in_result(tmp_path):
    index = osbuild.meta.Index(os.curdir)
    info = index.get_module_info("Stage", "org.osbuild.noop")
    stage = Stage(info, "source_opts", "build", "base", "options", "source_epoch")

    output_path = tmp_path / "jsonseq.log"
    output = "beginning-marker-vanishes\n" + "1" * 32_000 + "\nend-marker"
    build_result = BuildResult(stage, 0, output, {})
    with output_path.open("w") as fp:
        mon = JSONSeqMonitor(fp.fileno(), 1)
        mon.result(build_result)
    with output_path.open() as fp:
        line = fp.readline().strip("\x1e")
        json_result = json.loads(line)
    assert json_result["result"]["output"].startswith("[...1037 bytes hidden...]\n1111")
    assert json_result["result"]["output"].endswith("1111\nend-marker")


@unittest.skipUnless(RICH_AVAILABLE and PrettyMonitor, "rich not available")
@patch('osbuild.monitor.Console')
@patch('osbuild.monitor.RichProgress')
def test_pretty_monitor_upfront_stage_counting(mock_rich_progress, mock_console):
    """Test PrettyMonitor with upfront stage counting and total adjustment"""
    # Mock Rich components
    mock_progress_instance = Mock()
    mock_rich_progress.return_value = mock_progress_instance
    mock_console_instance = Mock()
    mock_console.return_value = mock_console_instance

    # Create mock pipelines and stages
    mock_pipeline1 = Mock()
    mock_pipeline1.name = "pipeline1"
    mock_pipeline1.id = "pipe1_id"
    mock_pipeline1.stages = [Mock(), Mock()]  # 2 stages

    mock_pipeline2 = Mock()
    mock_pipeline2.name = "pipeline2"
    mock_pipeline2.id = "pipe2_id"
    mock_pipeline2.stages = [Mock(), Mock(), Mock()]  # 3 stages

    mock_stage = Mock()
    mock_stage.name = "org.osbuild.test"
    mock_stage.id = "stage123"

    mock_success_result = Mock()
    mock_success_result.success = True
    mock_success_result.output = "Success"

    with tempfile.NamedTemporaryFile() as tmp:
        # Test monitor with 2 pipelines and 5 total stages (2+3)
        monitor = PrettyMonitor(tmp.fileno(), 2, 5)

        # Verify initial setup
        assert monitor.total_steps == 2  # Number of pipelines
        assert monitor.total_stages == 5
        assert monitor.completed_stages == 0

        # Test first pipeline
        monitor.begin(mock_pipeline1)
        assert monitor.current_pipeline_index == 1

        # Process 2 stages for pipeline 1
        for _ in range(2):
            monitor.stage(mock_stage)
            monitor.result(mock_success_result)

        # Finish first pipeline
        monitor.finish({"success": True, "name": "pipeline1"})
        assert monitor.completed_stages == 2

        # Test second pipeline
        monitor.begin(mock_pipeline2)
        assert monitor.current_pipeline_index == 2

        # Process 3 stages for pipeline 2
        for _ in range(3):
            monitor.stage(mock_stage)
            monitor.result(mock_success_result)

        # Finish second pipeline
        monitor.finish({"success": True, "name": "pipeline2"})
        assert monitor.completed_stages == 5

        # Verify Rich components were used correctly
        mock_progress_instance.start.assert_called_once()
        mock_progress_instance.stop.assert_called_once()
        mock_progress_instance.add_task.assert_called_once()

        # Should have 5 progress updates (one per stage)
        assert mock_progress_instance.update.call_count >= 5


@unittest.skipUnless(RICH_AVAILABLE and PrettyMonitor, "rich not available")
@patch('osbuild.monitor.Console')
@patch('osbuild.monitor.RichProgress')
def test_pretty_monitor_failure_tracking(mock_rich_progress, mock_console):
    """Test PrettyMonitor failure tracking and pipeline-level reporting"""
    # Mock Rich components
    mock_progress_instance = Mock()
    mock_rich_progress.return_value = mock_progress_instance
    mock_console_instance = Mock()
    mock_console.return_value = mock_console_instance

    # Create mock pipeline and stages
    mock_pipeline = Mock()
    mock_pipeline.name = "failing-pipeline"
    mock_pipeline.id = "pipe_id"
    mock_pipeline.stages = [Mock(), Mock(), Mock()]  # 3 stages

    mock_stage = Mock()
    mock_stage.name = "org.osbuild.test"
    mock_stage.id = "stage123"

    mock_success_result = Mock()
    mock_success_result.success = True
    mock_success_result.output = "Success"

    mock_failed_result = Mock()
    mock_failed_result.success = False
    mock_failed_result.output = "Failed with error"

    with tempfile.NamedTemporaryFile() as tmp:
        # Test monitor with 1 pipeline and 3 stages
        monitor = PrettyMonitor(tmp.fileno(), 1, 3)

        # Start pipeline
        monitor.begin(mock_pipeline)

        # First stage succeeds
        monitor.stage(mock_stage)
        monitor.result(mock_success_result)
        assert len(monitor.failed_stages) == 0

        # Second stage fails
        monitor.stage(mock_stage)
        monitor.result(mock_failed_result)
        assert len(monitor.failed_stages) == 1

        # Third stage succeeds
        monitor.stage(mock_stage)
        monitor.result(mock_success_result)

        # Finish pipeline with failure
        monitor.finish({"success": False, "name": "failing-pipeline"})

        # Verify failure was tracked properly
        assert monitor.completed_stages == 3

        # Should have printed failure details to console for the failed pipeline
        assert mock_console_instance.print.call_count >= 1
