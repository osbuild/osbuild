"""Wrapper module for output formatting."""

import sys
from typing import Dict


class VT:
    """Video terminal output, disables formatting when stdout is not a tty."""

    isatty: bool

    escape_sequences: Dict[str, str] = {
        "reset": "\033[0m",

        "bold": "\033[1m",

        "red": "\033[31m",
        "green": "\033[32m",
    }

    def __init__(self) -> None:
        self.isatty = sys.stdout.isatty()

    def __getattr__(self, name: str) -> str:
        if not self.isatty:
            return ""

        return self.escape_sequences[name]


fmt = VT()
