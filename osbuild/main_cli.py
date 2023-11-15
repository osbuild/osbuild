"""Entrypoints for osbuild

This module contains the application and API entrypoints of `osbuild`, the
command-line-interface to osbuild. The `osbuild_cli()` entrypoint can be safely
used from tests to run the cli.
"""


import argparse
import json
import os
import sys
import typing
from typing import List

import osbuild
import osbuild.meta
import osbuild.monitor
from osbuild.meta import ValidationResult
from osbuild.objectstore import ObjectStore
from osbuild.pipeline import Manifest
from osbuild.util.parsing import parse_size
from osbuild.util.term import fmt as vt


def parse_manifest(path: str) -> dict:
    if path == "-":
        manifest = json.load(sys.stdin)
    else:
        with open(path, encoding="utf8") as f:
            manifest = json.load(f)

    return manifest


def show_validation(result: ValidationResult, name: str) -> None:
    if name == "-":
        name = "<stdin>"

    print(f"{vt.bold}{name}{vt.reset} ", end='')

    if result:
        print(f"is {vt.bold}{vt.green}valid{vt.reset}")
        return

    print(f"has {vt.bold}{vt.red}errors{vt.reset}:")
    print("")

    for error in result:
        print(f"{vt.bold}{error.id}{vt.reset}:")
        print(f"  {error.message}\n")


def export(name_or_id: str, output_directory: str, store: ObjectStore, manifest: Manifest) -> None:
    pipeline = manifest[name_or_id]
    obj = store.get(pipeline.id)
    dest = os.path.join(output_directory, name_or_id)

    skip_preserve_owner = \
        os.getenv("OSBUILD_EXPORT_FORCE_NO_PRESERVE_OWNER") == "1"
    os.makedirs(dest, exist_ok=True)
    obj.export(dest, skip_preserve_owner=skip_preserve_owner)


@typing.no_type_check  # see https://github.com/python/typeshed/issues/3107
def parse_arguments(sys_argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="osbuild",
                                     description="Build operating system images")

    parser.add_argument("manifest_path", metavar="MANIFEST",
                        help="json file containing the manifest that should be built, or a '-' to read from stdin")
    parser.add_argument("--store", metavar="DIRECTORY", type=os.path.abspath,
                        default=".osbuild",
                        help="directory where intermediary os trees are stored")
    parser.add_argument("-l", "--libdir", metavar="DIRECTORY", type=os.path.abspath, default="/usr/lib/osbuild",
                        help="directory containing stages, assemblers, and the osbuild library")
    parser.add_argument("--cache-max-size", metavar="SIZE", type=parse_size, default=None,
                        help="maximum size of the cache (bytes) or 'unlimited' for no restriction")
    parser.add_argument(
        "--checkpoint",
        metavar="ID",
        action="append",
        type=str,
        default=None,
        help="stage to commit to the object store during build (can be passed multiple times), accepts globs")
    parser.add_argument("--export", metavar="ID", action="append", type=str, default=[],
                        help="object to export, can be passed multiple times")
    parser.add_argument("--json", action="store_true",
                        help="output results in JSON format")
    parser.add_argument("--json-mode", metavar="MODE", type=str, default="batch",
                        help=("output mode for JSON format; "
                              "'batch' (default if unspecified) mode prints all the results when the build ends "
                              "'jsonseq' prints status updates while building with each line being a JSON object"))
    parser.add_argument("--output-directory", metavar="DIRECTORY", type=os.path.abspath,
                        help="directory where result objects are stored")
    parser.add_argument("--inspect", action="store_true",
                        help="return the manifest in JSON format including all the ids")
    parser.add_argument("--monitor", metavar="NAME", default=None,
                        help="name of the monitor to be used")
    parser.add_argument("--monitor-fd", metavar="FD", type=int, default=sys.stdout.fileno(),
                        help="file descriptor to be used for the monitor")
    parser.add_argument("--stage-timeout", type=int, default=None,
                        help="set the maximal time (in seconds) each stage is allowed to run")
    parser.add_argument("--version", action="version",
                        help="return the version of osbuild",
                        version="%(prog)s " + osbuild.__version__)
    # nargs='?' const='*' means `--break` is equivalent to `--break=*`
    parser.add_argument("--break", dest='debug_break', type=str, nargs='?', const='*',
                        help="open debug shell when executing stage. Accepts stage name or id or * (for all)")

    return parser.parse_args(sys_argv[1:])


# pylint: disable=too-many-branches,too-many-return-statements,too-many-statements
def osbuild_cli() -> int:
    args = parse_arguments(sys.argv)
    desc = parse_manifest(args.manifest_path)

    index = osbuild.meta.Index(args.libdir)

    # detect the format from the manifest description
    info = index.detect_format_info(desc)
    if not info:
        print("Unsupported manifest format")
        return 2
    fmt = info.module

    # first thing is validation of the manifest
    res = fmt.validate(desc, index)
    if not res:
        if args.json or args.inspect:
            json.dump(res.as_dict(), sys.stdout)
            sys.stdout.write("\n")
        else:
            show_validation(res, args.manifest_path)
        return 2

    manifest = fmt.load(desc, index)

    exports = set(args.export)
    unresolved = [e for e in exports if e not in manifest]
    if unresolved:
        for name in unresolved:
            print(f"Export {vt.bold}{name}{vt.reset} not found!")
        print(f"{vt.reset}{vt.bold}{vt.red}Failed{vt.reset}")
        return 1

    if args.checkpoint:
        marked = manifest.mark_checkpoints(args.checkpoint)
        if not marked:
            print("No checkpoints matched provided patterns!")
            print(f"{vt.reset}{vt.bold}{vt.red}Failed{vt.reset}")
            return 1

    if args.inspect:
        result = fmt.describe(manifest, with_id=True)
        json.dump(result, sys.stdout)
        sys.stdout.write("\n")
        return 0

    output_directory = args.output_directory

    if exports and not output_directory:
        print("Need --output-directory for --export")
        return 1

    monitor_name = args.monitor
    if not monitor_name:
        monitor_name = "NullMonitor" if args.json else "LogMonitor"

    outfd = sys.stdout.fileno()
    if args.json:
        if args.json_mode == "jsonseq":
            monitor = osbuild.monitor.JSONSeqMonitor(outfd, manifest)
            monitor.log("start", origin="org.osbuild.main")
        elif args.json_mode == "batch":
            monitor = osbuild.monitor.NullMonitor(outfd)
        else:
            print(f"unknown json mode {args.json_mode}")
            return 1
    else:
        monitor = osbuild.monitor.make(monitor_name, args.monitor_fd)

    try:
        with ObjectStore(args.store) as object_store:
            if args.cache_max_size is not None:
                object_store.maximum_size = args.cache_max_size

            stage_timeout = args.stage_timeout
            debug_break = args.debug_break

            pipelines = manifest.depsolve(object_store, exports)

            manifest.download(object_store, monitor, args.libdir)

            r = manifest.build(
                object_store,
                pipelines,
                monitor,
                args.libdir,
                debug_break,
                stage_timeout=stage_timeout
            )

            if r["success"] and exports:
                for pid in exports:
                    export(pid, output_directory, object_store, manifest)

            if args.json:
                if args.json_mode == "batch":
                    r = fmt.output(manifest, r, object_store)
                    json.dump(r, sys.stdout)
                    sys.stdout.write("\n")
            else:
                if r["success"]:
                    for name, pl in manifest.pipelines.items():
                        print(f"{name + ':': <10}\t{pl.id}")
                else:
                    print()
                    print(f"{vt.reset}{vt.bold}{vt.red}Failed{vt.reset}")

            return 0 if r["success"] else 1

    except KeyboardInterrupt:
        print()
        print(f"{vt.reset}{vt.bold}{vt.red}Aborted{vt.reset}")
        return 130
