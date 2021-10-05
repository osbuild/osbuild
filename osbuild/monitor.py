"""
Monitor pipeline activity

The osbuild `Pipeline` class supports monitoring of its activities
by providing a monitor object that implements the `BaseMonitor`
interface. During the execution of the pipeline various functions
are called on the monitor object at certain events. Consult the
`BaseMonitor` class for the description of all available events.
"""

import abc
import datetime
import hashlib
import json
import os
import sys
import time
from typing import Dict, Optional, Set

import osbuild
from osbuild.util.term import fmt as vt


class Context:
    """Context for a single log line. Automatically calculates hash/id when read."""

    def __init__(self,
                 origin: Optional[str] = None,
                 pipeline: Optional[osbuild.Pipeline] = None,
                 stage: Optional[osbuild.Stage] = None):
        self._origin = origin
        self._pipeline_name = pipeline.name if pipeline else None
        self._pipeline_id = pipeline.id if pipeline else None
        self._stage_name = stage.name if stage else None
        self._stage_id = stage.id if stage else None
        self._id = None
        self._id_history: Set[str] = set()

    @property
    def origin(self):
        return self._origin

    @origin.setter
    def origin(self, origin: str):
        self._id = None
        self._origin = origin

    @property
    def pipeline_name(self):
        return self._pipeline_name

    @property
    def pipeline_id(self):
        return self._pipeline_id

    def pipeline(self, pipeline: osbuild.Pipeline):
        self._id = None
        self._pipeline_name = pipeline.name
        self._pipeline_id = pipeline.id

    @property
    def stage_name(self):
        return self._stage_name

    @property
    def stage_id(self):
        return self._stage_id

    def stage(self, stage: osbuild.Stage):
        self._id = None
        self._stage_name = stage.name
        self._stage_id = stage.id

    @property
    def id(self):
        if self._id is None:
            self._id = hashlib.sha256(json.dumps(self._dict()).encode()).hexdigest()
        return self._id

    def _dict(self):
        return {
            "origin": self._origin,
            "pipeline": {
                "name": self._pipeline_name,
                "id": self._pipeline_id,
                "stage": {
                    "name": self._stage_name,
                    "id": self._stage_id,
                },
            },
        }

    def as_dict(self):
        d = self._dict()
        ctxid = self.id
        if ctxid in self._id_history:
            return {"id": self.id}
        d["id"] = self.id
        self._id_history.add(self.id)
        return d


class Progress:
    def __init__(self, name: str, total: int, unit: Optional[str] = None):
        self.name = name
        self.total = total
        self.unit = unit
        self.done = None
        self._sub_progress: Optional[Progress] = None

    def incr(self, depth=0):
        if depth > 0:
            self._sub_progress.incr(depth - 1)
        else:
            if self.done is None:
                self.done = 0
            else:
                self.done += 1
            if self._sub_progress:
                self._sub_progress.reset()

    def reset(self):
        self.done = None
        if self._sub_progress:
            self._sub_progress.reset()

    def sub_progress(self, prog: "Progress"):
        self._sub_progress = prog

    def as_dict(self):
        d = {
            "name": self.name,
            "total": self.total,
            "done": self.done,
            "unit": self.unit,
        }
        if self._sub_progress:
            d["progress"] = self._sub_progress.as_dict()
        return d


class LogLine:
    """A single JSON serializable log line

    Create a single log line with a given message, error message, context, and progress objects.
    All arguments are optional. A timestamp is added to the dictionary when calling the 'as_dict()' method.
    """

    def __init__(self, *,
                 message: Optional[str] = None,
                 error: Optional[str] = None,
                 context: Optional[Context] = None,
                 progress: Optional[Progress] = None):
        self.message = message
        self.error = error
        self.context = context
        self.progress = progress

    def as_dict(self):
        return {
            "message": self.message,
            "error": self.error,
            "context": self.context.as_dict(),
            "progress": self.progress.as_dict(),
            "timestamp": time.time(),
        }


class TextWriter:
    """Helper class for writing text to file descriptors"""

    def __init__(self, fd: int):
        self.fd = fd
        self.isatty = os.isatty(fd)

    def term(self, text, *, clear=False):
        """Write text if attached to a terminal."""
        if not self.isatty:
            return

        if clear:
            self.write(vt.reset)

        self.write(text)

    def write(self, text: str):
        """Write all of text to the log file descriptor"""
        data = text.encode("utf-8")
        n = len(data)
        while n:
            k = os.write(self.fd, data)
            n -= k
            if n:
                data = data[n:]


class BaseMonitor(abc.ABC):
    """Base class for all pipeline monitors"""

    def __init__(self, fd: int):
        """Logging will be done to file descriptor `fd`"""
        self.out = TextWriter(fd)

    def begin(self, pipeline: osbuild.Pipeline):
        """Called once at the beginning of a pipeline"""

    def finish(self, results: Dict):
        """Called at the very end of a pipeline"""

    def stage(self, stage: osbuild.Stage):
        """Called when a stage is being built"""

    def assembler(self, assembler: osbuild.Stage):
        """Called when an assembler is being built"""

    def result(self, result: osbuild.pipeline.BuildResult):
        """Called when a module (stage/assembler) is done with its result"""

    def log(self, message: str, origin: Optional[str] = None):
        """Called for all module log outputs"""


class NullMonitor(BaseMonitor):
    """Monitor class that does not report anything"""


class LogMonitor(BaseMonitor):
    """Monitor that follows the log output of modules

    This monitor will print a header with `name: id` followed
    by the options for each module as it is being built. The
    full log messages of the modules will be printed as soon as
    they become available.
    The constructor argument `fd` is a file descriptor, where
    the log will get written to. If `fd`  is a `TTY`, escape
    sequences will be used to highlight sections of the log.
    """

    def __init__(self, fd: int):
        super().__init__(fd)
        self.timer_start = 0

    def result(self, result):
        duration = int(time.time() - self.timer_start)
        self.out.write(f"\n⏱  Duration: {duration}s\n")

    def begin(self, pipeline):
        self.out.term(vt.bold, clear=True)
        self.out.write(f"Pipeline {pipeline.name}: {pipeline.id}")
        self.out.term(vt.reset)
        self.out.write("\n")
        self.out.write("Build\n  root: ")
        if pipeline.build:
            self.out.write(pipeline.build)
        else:
            self.out.write("<host>")
        self.out.write(f"\n  runner: {pipeline.runner.name} ({pipeline.runner.exec})")
        source_epoch = pipeline.source_epoch
        if source_epoch is not None:
            timepoint = datetime.datetime.fromtimestamp(source_epoch).strftime('%c')
            self.out.write(f"\n  source-epoch: {timepoint} [{source_epoch}]")
        self.out.write("\n")

    def stage(self, stage):
        self.module(stage)

    def assembler(self, assembler):
        self.out.term(vt.bold, clear=True)
        self.out.write("Assembler ")
        self.out.term(vt.reset)

        self.module(assembler)

    def module(self, module):
        options = module.options or {}
        title = f"{module.name}: {module.id}"

        self.out.term(vt.bold, clear=True)
        self.out.write(title)
        self.out.term(vt.reset)
        self.out.write(" ")

        json.dump(options, self.out, indent=2)
        self.out.write("\n")

        self.timer_start = time.time()

    def log(self, message, origin: Optional[str] = None):
        self.out.write(message)


class JSONProgressMonitor(BaseMonitor):
    """Monitor that prints the log output of modules wrapped in a JSON object with context and progress metadata"""

    def __init__(self, fd: int, manifest: osbuild.Manifest):
        super().__init__(fd)
        self._ctx_ids: Set[str] = set()
        self._progress = Progress("pipelines", len(manifest.pipelines))
        self._context = Context(origin="org.osbuild")

    def result(self, result):
        pass

    def begin(self, pipeline: osbuild.Pipeline):
        self._context.pipeline(pipeline)
        self._progress.sub_progress(Progress("stages", len(pipeline.stages)))
        self._progress.incr()

    def stage(self, stage: osbuild.Stage):
        self._context.stage(stage)
        self._progress.incr(depth=1)

    def assembler(self, assembler):
        self.module(assembler)

    def module(self, module):
        self.stage(module)

    def log(self, message, origin: Optional[str] = None):
        oo = self._context.origin
        if origin is not None:
            self._context.origin = origin
        line = LogLine(message=message, context=self._context, progress=self._progress)
        json.dump(line.as_dict(), self.out)
        self.out.write("\n")
        self._context.origin = oo


def make(name, fd):
    module = sys.modules[__name__]
    monitor = getattr(module, name, None)
    if not monitor:
        raise ValueError(f"Unknown monitor: {name}")
    if not issubclass(monitor, BaseMonitor):
        raise ValueError(f"Invalid monitor: {name}")
    return monitor(fd)
