"""
Monitor pipeline activity

The osbuild `Pipeline` class supports monitoring of its activities
by providing a monitor object that implements the `BaseMonitor`
interface. During the execution of the pipeline various functions
are called on the monitor object at certain events. Consult the
`BaseMonitor` class for the description of all available events.
"""

import abc
import json
import os
import sys
import time

from typing import Dict, Any

import osbuild


RESET = "\033[0m"
BOLD = "\033[1m"


class TextWriter:
    """Helper class for writing text to file descriptors"""

    def __init__(self, fd: int) -> None:
        self.fd = fd
        self.isatty = os.isatty(fd)

    def term(self, text: str, *, clear: bool = False) -> None:
        """Write text if attached to a terminal."""
        if not self.isatty:
            return

        if clear:
            self.write(RESET)

        self.write(text)

    def write(self, text: str) -> None:
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

    def __init__(self, fd: int) -> None:
        """Logging will be done to file descriptor `fd`"""
        self.out = TextWriter(fd)

    def begin(self, pipeline: osbuild.Pipeline) -> None:
        """Called once at the beginning of a build"""

    def finish(self, result: Dict[str, Any]) -> None:
        """Called at the very end of the build"""

    def stage(self, stage: osbuild.Stage) -> None:
        """Called when a stage is being built"""

    def assembler(self, assembler: osbuild.Stage) -> None:
        """Called when an assembler is being built"""

    def result(self, result: osbuild.pipeline.BuildResult) -> None:
        """Called when a module is done with its result"""

    def log(self, message: str) -> None:
        """Called for all module log outputs"""


class NullMonitor(BaseMonitor):
    """Monitor class that does not report anything"""


class LogMonitor(BaseMonitor):
    """Monitor that follows show the log output of modules

    This monitor will print a header with `name: id` followed
    by the options for each module as it is being built. The
    full log messages of the modules will be print as soon as
    they become available.
    The constructor argument `fd` is a file descriptor, where
    the log will get written to. If `fd`  is a `TTY`, escape
    sequences will be used to highlight sections of the log.
    """

    def __init__(self, fd: int) -> None:
        super().__init__(fd)

        self.timer_start = 0.0

    def result(self, result: osbuild.pipeline.BuildResult) -> None:
        duration = int(time.time() - self.timer_start)
        self.out.write(f"\n⏱  Duration: {duration}s\n")

    def begin(self, pipeline: osbuild.pipeline.Pipeline) -> None:
        self.out.term(BOLD, clear=True)
        self.out.write(f"Pipeline {pipeline.name}: {pipeline.id}")
        self.out.term(RESET)
        self.out.write("\n")

    def stage(self, stage: osbuild.pipeline.Stage) -> None:
        self.module(stage)

    def assembler(self, assembler: osbuild.pipeline.Stage) -> None:
        self.out.term(BOLD, clear=True)
        self.out.write("Assembler ")
        self.out.term(RESET)

        self.module(assembler)

    def module(self, module: osbuild.pipeline.Stage) -> None:
        options = module.options or {}
        title = f"{module.name}: {module.id}"

        self.out.term(BOLD, clear=True)
        self.out.write(title)
        self.out.term(RESET)
        self.out.write(" ")

        json.dump(options, self.out, indent=2)
        self.out.write("\n")

        self.timer_start = time.time()

    def log(self, message: str) -> None:
        self.out.write(message)


def make(name, fd: int) -> BaseMonitor:
    module = sys.modules[__name__]
    monitor = getattr(module, name, None)
    if not monitor:
        raise ValueError(f"Unknown monitor: {name}")
    if not issubclass(monitor, BaseMonitor):
        raise ValueError(f"Invalid monitor: {name}")
    return monitor(fd)
