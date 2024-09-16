"""Development entry point for osbuild

This is used while building a container with `make container.dev`
This allows to attach the debugger even when more services
of the stack are running in parallel
"""
import os

import debugpy
import pydevd_pycharm

from osbuild.main_cli import osbuild_cli


def osbuild_dev():
    debug_port = os.getenv("OSBUILD_PYCHARM_DEBUG_PORT")
    if debug_port:
        debug_host = os.getenv("OSBUILD_PYCHARM_DEBUG_HOST", 'host.docker.internal')
        print("Connecting to debugger...")
        pydevd_pycharm.settrace(debug_host, port=int(debug_port), stdoutToServer=True, stderrToServer=True)

    debug_port = os.getenv("OSBUILD_DEBUGPY_DEBUG_PORT")
    if debug_port:
        debug_host = os.getenv("OSBUILD_DEBUGPY_DEBUG_HOST", 'host.docker.internal')
        print("Connecting to debugger...")
        debugpy.listen(debug_host, port=int(debug_port))

    osbuild_cli()
