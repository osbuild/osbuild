"""
Monitor pipeline activity

The osbuild `Pipeline` class supports monitoring of its activities
by providing a monitor object that implements the `BaseMonitor`
interface. During the execution of the pipeline various functions
are called on the monitor object at certain events. Consult the
`BaseMonitor` class for the description of all available events.
"""

import abc
import copy
import datetime
import hashlib
import json
import os
import sys
import time
from typing import Dict, Optional, Set

import osbuild
from osbuild.util.term import fmt as vt


def omitempty(d: dict):
    """ Omit None and empty string ("") values from the given dict """
    for k, v in list(d.items()):
        if v is None or v == "":
            del d[k]
        elif isinstance(v, dict):
            omitempty(v)
    return d


class Context:
    """Context for a single log entry. Automatically calculates hash/id when read."""

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

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        # reset "_id" on any write so that the hash is automatically recalculated
        if name != "_id":
            super().__setattr__("_id", None)

    def with_origin(self, origin: Optional[str]) -> "Context":
        """
        Return a Context with the given origin but otherwise identical.

        Note that if the origin is empty or same it will return self.
        """
        if origin is None or origin == self._origin:
            return self
        ctx = copy.copy(self)
        ctx.set_origin(origin)
        return ctx

    @property
    def origin(self):
        return self._origin

    def set_origin(self, origin: str):
        self._origin = origin

    @property
    def pipeline_name(self):
        return self._pipeline_name

    @property
    def pipeline_id(self):
        return self._pipeline_id

    def set_pipeline(self, pipeline: osbuild.Pipeline):
        self._pipeline_name = pipeline.name
        self._pipeline_id = pipeline.id

    @property
    def stage_name(self):
        return self._stage_name

    @property
    def stage_id(self):
        return self._stage_id

    def set_stage(self, stage: osbuild.Stage):
        self._stage_name = stage.name
        self._stage_id = stage.id

    @property
    def id(self):
        if self._id is None:
            self._id = hashlib.sha256(
                json.dumps(self._dict(), sort_keys=True).encode()).hexdigest()
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
    """Progress represents generic progress information.

    A progress can contain a sub_progress to track more
    nested progresses. Any increment of a parent progress
    will the reset the sub_progress to None and a new
    sub_progress needs to be provided.

    Keyword arguments:
    name  -- user visible name for the progress
    total -- total steps required to finish the progress
    """

    def __init__(self, name: str, total: int):
        self.name = name
        self.total = total
        self.done = 0
        self.sub_progress: Optional[Progress] = None

    def incr(self):
        """Increment the "done" count"""
        self.done += 1
        if self.sub_progress:
            self.sub_progress = None

    def as_dict(self):
        d = {
            "name": self.name,
            "total": self.total,
            "done": self.done,
        }
        if self.sub_progress:
            d["progress"] = self.sub_progress.as_dict()
        return d


def log_entry(message: Optional[str] = None,
              context: Optional[Context] = None,
              progress: Optional[Progress] = None) -> dict:
    """
    Create a single log entry dict with a given message, context, and progress objects.
    All arguments are optional. A timestamp is added to the message.
    """
    # we probably want to add an (optional) error message here too once the
    # monitors support that
    return omitempty({
        "message": message,
        "context": context.as_dict() if context else None,
        "progress": progress.as_dict() if progress else None,
        "timestamp": time.time(),
    })


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

    def __init__(self, fd: int, manifest: Optional[osbuild.Manifest] = None) -> None:
        """Logging will be done to file descriptor `fd`"""
        self.out = TextWriter(fd)
        self.manifest = manifest

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

    def __init__(self, fd: int, manifest: Optional[osbuild.Manifest] = None):
        super().__init__(fd, manifest)
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
        if pipeline.runner:
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


class JSONSeqMonitor(BaseMonitor):
    """Monitor that prints the log output of modules wrapped in json-seq objects with context and progress metadata"""

    def __init__(self, fd: int, manifest: osbuild.Manifest):
        super().__init__(fd, manifest)
        self._ctx_ids: Set[str] = set()
        self._progress = Progress("pipelines/sources", len(manifest.pipelines) + len(manifest.sources))
        self._context = Context(origin="org.osbuild")

    def begin(self, pipeline: osbuild.Pipeline):
        self._context.set_pipeline(pipeline)
        if pipeline.stages:
            self._progress.sub_progress = Progress("stages", len(pipeline.stages))
        self.log(f"Starting pipeline {pipeline.name}", origin="osbuild.monitor")

    # finish is for pipelines
    def finish(self, results: dict):
        self._progress.incr()
        self.log(f"Finished pipeline {results['name']}", origin="osbuild.monitor")

    def stage(self, stage: osbuild.Stage):
        self._module(stage)

    def assembler(self, assembler: osbuild.Stage):
        self._module(assembler)

    def _module(self, module: osbuild.Stage):
        self._context.set_stage(module)
        self.log(f"Starting module {module.name}", origin="osbuild.monitor")

    # result is for modules
    def result(self, result: osbuild.pipeline.BuildResult):
        # we may need to check pipeline ids here in the future
        if self._progress.sub_progress:
            self._progress.sub_progress.incr()
        self.log(f"Finished module {result.name}", origin="osbuild.monitor")

    def log(self, message, origin: Optional[str] = None):
        entry = log_entry(message, self._context.with_origin(origin), self._progress)
        self._jsonseq(entry)

    def _jsonseq(self, entry):
        # follow rfc7464 (application/json-seq)
        self.out.write("\x1e")
        json.dump(entry, self.out)
        self.out.write("\n")


def make(name, fd, manifest):
    module = sys.modules[__name__]
    monitor = getattr(module, name, None)
    if not monitor:
        raise ValueError(f"Unknown monitor: {name}")
    if not issubclass(monitor, BaseMonitor):
        raise ValueError(f"Invalid monitor: {name}")
    return monitor(fd, manifest)
