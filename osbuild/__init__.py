"""OSBuild Module

The `osbuild` module provides access to the internal features of OSBuild. It
provides parsers for the input and output formats of osbuild, access to shared
infrastructure of osbuild stages, as well as a pipeline executor.

The utility module `osbuild.util` provides access to common functionality
independent of osbuild but used across the osbuild codebase.
"""

from .formats.v1 import load, load_build
from .pipeline import Assembler, Pipeline, Stage


__all__ = [
    "Assembler",
    "load",
    "load_build",
    "Pipeline",
    "Stage",
]
