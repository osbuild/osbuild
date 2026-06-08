#!/usr/bin/python3
"""Write a GRUB2 drop-in configuration file.

This stage writes a grub2 configuration snippet to a configurable
location (tree:// or mount://). The primary use case is writing
console.cfg for bootupd-managed bootloaders, but the path is
configurable to support other drop-in files.

The config options support serial, terminal_input, and
terminal_output settings matching the org.osbuild.grub2 stage.
"""
import os
import sys

import osbuild.api
from osbuild.util import parsing


def generate_grub2_dropin(config, file_path):
    """Write grub2 commands derived from config to file_path."""
    cmds = []
    serial = config.get("serial")
    if serial:
        cmds.append(serial)
    terminal_input = config.get("terminal_input")
    if terminal_input:
        cmds.append("terminal_input " + " ".join(terminal_input))
    terminal_output = config.get("terminal_output")
    if terminal_output:
        cmds.append("terminal_output " + " ".join(terminal_output))

    content = "\n".join(cmds) + "\n" if cmds else ""

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding="utf8") as f:
        f.write(content)


def main(args, options):
    config = options.get("config", {})
    file_path = parsing.parse_location(options["path"], args)

    generate_grub2_dropin(config, file_path)
    return 0


if __name__ == "__main__":
    _args = osbuild.api.arguments()
    r = main(_args, _args["options"])
    sys.exit(r)
