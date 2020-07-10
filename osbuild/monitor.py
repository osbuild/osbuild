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

from typing import Dict

import osbuild


RESET = "\033[0m"
BOLD = "\033[1m"


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
            self.write(RESET)

        self.write(text)

    def write(self, text: str):
        """Write all of text to the log file descriptor"""
        data = text.encode("utf-8")
        n = len(data)
        while n:
            k = os.write(self.fd, data)
            n -= k
            if n:
                text = data[n:]


class BaseMonitor(abc.ABC):
    """Base class for all pipeline monitors"""

    def __init__(self, fd: int):
        """Logging will be done to file descriptor `fd`"""
        self.out = TextWriter(fd)

    def begin(self, pipeline: osbuild.Pipeline):
        """Called once at the beginning of a build"""

    def finish(self, result: Dict):
        """Called at the very end of the build"""

    def stage(self, stage: osbuild.Stage):
        """Called when a stage is being built"""

    def assembler(self, assembler: osbuild.Assembler):
        """Called when an assembler is being built"""

    def result(self, result: osbuild.pipeline.BuildResult):
        """Called when a module is done with its result"""

    def log(self, message: str):
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
    def stage(self, stage):
        self.module(stage)

    def assembler(self, assembler):
        self.out.term(BOLD, clear=True)
        self.out.write("Assembler ")
        self.out.term(RESET)

        self.module(assembler)

    def module(self, module):
        options = module.options or {}
        title = f"{module.name}: {module.id}"

        self.out.term(BOLD, clear=True)
        self.out.write(title)
        self.out.term(RESET)
        self.out.write(" ")

        json.dump(options, self.out, indent=2)
        self.out.write("\n")

    def log(self, message):
        self.out.write(message)


class JsonLinesMonitor(BaseMonitor):
    """Monitor that streams status information as JSON Lines

    A Monitor that writes JSON messages before and after
    a specific module is being built, so that clients can
    keep track of the status during the build process.
    """
    def __init__(self, fd: int):
        super().__init__(fd)
        self.modules = {}

    def begin(self, pipeline):

        def register(module):
            count = len(self.modules) + 1
            self.modules[module.id] = count

        def collect(pl):
            if pl.build:
                collect(pl.build)

            for stage in pl.stages:
                register(stage)

            if pl.assembler:
                register(pl.assembler)

        collect(pipeline)

    def stage(self, stage):
        self.module(stage, "stage")

    def assembler(self, assembler):
        self.module(assembler, "assembler")

    def module(self, module, module_type):
        module_id = module.id
        number = self.modules[module_id]

        status = {
            "type": "progress",
            "data": {
                "module": {
                    "type": module_type,
                    "name": module.name,
                    "id": module_id
                },
                "progress": {
                    "current": number,
                    "total": len(self.modules)
                }
            }
        }

        self.send(status)

    def send(self, js):
        json.dump(js, self.out)
        self.out.write("\n")


def make(name, fd):
    module = sys.modules[__name__]
    monitor = getattr(module, name, None)
    if not monitor:
        raise ValueError(f"Unknown monitor: {name}")
    if not issubclass(monitor, BaseMonitor):
        raise ValueError(f"Invalid monitor: {name}")
    return monitor(fd)
