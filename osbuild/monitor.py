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
from threading import Lock
from typing import Dict, List, Optional, Set, Union

import osbuild
from osbuild.pipeline import BuildResult, DownloadResult
from osbuild.util.term import fmt as vt

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )
    from rich.progress import (
        Progress as RichProgress,
    )
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


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
        ctx.origin = origin
        return ctx

    @property
    def origin(self):
        return self._origin

    @origin.setter
    def origin(self, origin: str):
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
              progress: Optional[Progress] = None,
              result: Union[BuildResult, DownloadResult, None] = None,
              ) -> dict:
    """
    Create a single log entry dict with a given message, context, and progress objects.
    All arguments are optional. A timestamp is added to the message.
    """
    # we probably want to add an (optional) error message here too once the
    # monitors support that
    return omitempty({
        "message": message,
        "result": result.as_dict() if result else None,
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

    def __init__(self, fd: int, _steps: int = 0, _stages: int = 0) -> None:
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

    def result(self, result: Union[BuildResult, DownloadResult]) -> None:
        """Called when a module (stage/assembler) is done with its result"""

    # note that this should be re-entrant
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

    def __init__(self, fd: int, total_steps: int = 0, _: int = 0):
        super().__init__(fd, total_steps)
        self.timer_start = 0

    def result(self, result: Union[BuildResult, DownloadResult]) -> None:
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

    def __init__(self, fd: int, total_steps: int = 0, _: int = 0):
        super().__init__(fd, total_steps)
        self._ctx_ids: Set[str] = set()
        self._progress = Progress("pipelines/sources", total_steps)
        self._context = Context(origin="org.osbuild")
        self._jsonseq_mu = Lock()

    def begin(self, pipeline: osbuild.Pipeline):
        self._context.set_pipeline(pipeline)
        if pipeline.stages:
            self._progress.sub_progress = Progress(f"pipeline: {pipeline.name}", len(pipeline.stages))
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

    def result(self, result: Union[BuildResult, DownloadResult]) -> None:
        """ Called when the module (stage or download) is finished

        This will stream a log entry that the stage finished and the result
        is available via the json-seq monitor as well. Note that while the
        stage output is part of the result it may be abbreviated. To get
        an entire buildlog the consumer needs to simply log the calls to
        "log()" which contain more detailed information as well.
        """
        # we may need to check pipeline ids here in the future
        if self._progress.sub_progress:
            self._progress.sub_progress.incr()

        # Limit the output in the json pipeline to a "reasonable"
        # length. We ran into an issue from a combination of a stage
        # that produce tons of output (~256 kb, see issue#1976) and
        # the consumer that used a golang scanner with a max default
        # buffer of 64kb before erroring.
        #
        # Consumers can collect the individual log lines on their own
        # if desired via the "log()" method.
        max_output_len = 31_000
        if len(result.output) > max_output_len:
            removed = len(result.output) - max_output_len
            result.output = f"[...{removed} bytes hidden...]\n{result.output[removed:]}"

        self._jsonseq(log_entry(
            f"Finished module {result.name}",
            context=self._context.with_origin("osbuild.monitor"),
            progress=self._progress,
            # We should probably remove the "output" key from the result
            # as it is redundant, each output already generates a "log()"
            # message that is streamed to the client.
            result=result,
        ))

    def log(self, message, origin: Optional[str] = None):
        self._jsonseq(log_entry(
            message,
            context=self._context.with_origin(origin),
            progress=self._progress,
        ))

    def _jsonseq(self, entry: dict) -> None:
        with self._jsonseq_mu:
            # follow rfc7464 (application/json-seq)
            self.out.write("\x1e")
            json.dump(entry, self.out)
            self.out.write("\n")


class PrettyMonitor(BaseMonitor):  # pylint: disable=too-many-instance-attributes
    """Monitor that displays a clean progress bar interface using Rich

    This monitor provides a less verbose, visually appealing progress display
    tailored for build processes. It shows overall progress, current stage
    information, and timing with limited log output.
    """

    def __init__(self, fd: int, total_steps: int = 0, total_stages: int = 0):
        super().__init__(fd, total_steps)
        if not RICH_AVAILABLE:
            raise RuntimeError("PrettyMonitor requires python3-rich to be installed")

        # Setup rich console using the provided file descriptor
        # Note: We need to duplicate the fd to avoid closing it when Console closes
        dup_fd = os.dup(fd)
        self.console = Console(file=os.fdopen(dup_fd, "w"), force_terminal=True)
        self.stage_timer_start = 0
        self.timer_start = time.time()

        self.total_steps = total_steps
        self.completed_steps = 0

        self.total_stages = total_stages
        self.completed_stages = 0

        self.progress = RichProgress(
            SpinnerColumn(style="blue"),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=self.console,
            refresh_per_second=8,
        )
        self.progress.start()

        initial_desc = f"Building Stages: Total {self.total_stages} Stages"

        self.main_task = self.progress.add_task(
            initial_desc,
            total=self.total_stages,
            completed=0,
            start_time=self.timer_start,
        )

        self.pipeline: Optional[osbuild.Pipeline] = None
        self.current_pipeline_index = 0
        self.current_stage: Optional[str] = None
        self.step_start_time: float = 0

        self.failed_stages: List[Dict[str, Union[str, int, None]]] = []

    def begin(self, pipeline: osbuild.Pipeline):
        self.pipeline = pipeline
        self.step_start_time = time.time()
        self.current_pipeline_index += 1
        self.failed_stages.clear()

        if self.total_steps > 1 and self.total_stages > 0:
            progress_desc = (
                f"Building {self.total_stages} Stages (Pipeline"
                f" {self.current_pipeline_index}/{self.total_steps})"
            )
        elif self.total_stages > 0:
            progress_desc = f"Building {self.total_stages} Stages"
        else:
            progress_desc = "Building Stages"

        self.progress.update(self.main_task, description=progress_desc)

    def finish(self, results: Dict):
        self.completed_steps += 1

        pipeline_duration = int(time.time() - self.step_start_time)
        pipeline_success = results.get("success", False)
        status_color = "green" if pipeline_success else "red"
        status_text = (
            "[[yellow]🗸[/yellow]] Completed" if pipeline_success else "[■] Failed"
        )

        self.console.print(
            f"[{status_color}]{status_text}: Pipeline {results.get('name',
                                                                                  'Unknown')} [{self.current_pipeline_index}/{self.total_steps}] ({pipeline_duration}s)[/{status_color}]"
        )

        if not pipeline_success and self.failed_stages:
            self.console.print(
                f"\n[bold red]Pipeline {
                    results.get(
                        'name',
                        'Unknown')} failed with {
                    len(
                        self.failed_stages)} stage failure(s):[/bold red]"
            )
            for failure in self.failed_stages:
                if failure["output"]:
                    self.console.print(
                        Panel(
                            renderable=failure["output"],
                            title=f"[bold red]Stage Failure Details - {failure['stage']}[/bold red]",
                            border_style="red",
                            padding=(1, 2),
                        )
                    )

        if self.completed_steps >= self.total_steps:
            if self.progress:
                self.progress.update(self.main_task, completed=self.total_stages)
                self.progress.stop()

            duration = int(time.time() - self.timer_start)
            status_color = "green" if results.get("success", False) else "red"
            status_text = (
                "Build Completed Successfully"
                if results.get("success", False)
                else "Build Failed"
            )

            completion_panel = Panel(
                f"[bold {status_color}]{status_text}[/bold {status_color}]\n"
                f"[dim]Stages completed: {self.completed_stages}/{self.total_stages}[/dim]\n"
                f"[dim]Pipelines completed: {self.completed_steps}/{self.total_steps}[/dim]\n"
                f"[dim]Total time: {duration}s[/dim]"
                + (
                    f"\n[dim yellow]Errors encountered: {len(self.failed_stages)}[/dim yellow]"
                    if self.failed_stages
                    else ""
                ),
                title="Build Result",
                border_style=status_color,
                padding=(1, 2),
            )
            self.console.print(completion_panel)

    def stage(self, stage: osbuild.Stage):
        self._start_module(stage)

    def assembler(self, assembler: osbuild.Stage):
        self._start_module(assembler)

    def _start_module(self, module: osbuild.Stage):
        self.current_stage = module.name
        self.stage_timer_start = time.time()

        pipeline_name = self.pipeline.name if self.pipeline else "Unknown"
        current_stage_num = self.completed_stages + 1
        stage_desc = f"[{current_stage_num}/{self.total_stages}] {pipeline_name}: {self.current_stage}"

        self.progress.update(self.main_task, description=stage_desc)

    def result(self, result: Union[BuildResult, DownloadResult]) -> None:
        duration = int(time.time() - self.stage_timer_start)
        if not result.success:
            stage_info = f"[{self.completed_stages + 1}/{self.total_stages}] {self.current_stage}"
            self.failed_stages.append(
                {
                    "stage": self.current_stage,
                    "stage_info": stage_info,
                    "duration": duration,
                    "output": (
                        result.output.strip()
                        if result.output and result.output.strip()
                        else None
                    ),
                }
            )

        if self.progress and self.main_task is not None:
            self.progress.update(self.main_task, advance=1)
            self.completed_stages += 1
            pipeline_name = self.pipeline.name if self.pipeline else "Unknown"
            completion_desc = f"[[yellow]🗸[/yellow]] Completed [{
                self.completed_stages}/{
                self.total_stages}] {pipeline_name}: {
                self.current_stage}"
            if not result.success:
                completion_desc = f"[■] Failed at [{
                    self.completed_stages}/{
                    self.total_stages}] {pipeline_name}: {
                    self.current_stage}"

            self.progress.update(self.main_task, description=completion_desc)


def make(name: str, fd: int, total_steps: int, total_stages: int = 0) -> BaseMonitor:
    module = sys.modules[__name__]
    monitor = getattr(module, name, None)
    if not monitor:
        raise ValueError(f"Unknown monitor: {name}")
    if not issubclass(monitor, BaseMonitor):
        raise ValueError(f"Invalid monitor: {name}")
    return monitor(fd, total_steps, total_stages)
