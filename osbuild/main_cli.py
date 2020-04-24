"""Entrypoints for osbuild

This module contains the application and API entrypoints of `osbuild`, the
command-line-interface to osbuild. The `osbuild_cli()` entrypoint can be safely
used from tests to run the cli.
"""


import argparse
import json
import os
import sys

import osbuild
import osbuild.meta


RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"


def mark_checkpoints(pipeline, checkpoints):
    points = set(checkpoints)

    def mark_stage(stage):
        c = stage.id
        if c in points:
            stage.checkpoint = True
            points.remove(c)

    def mark_pipeline(pl):
        for stage in pl.stages:
            mark_stage(stage)
        if pl.build:
            mark_pipeline(pl.build)

    mark_pipeline(pipeline)
    return points


def parse_manifest(path):
    if path == "-":
        manifest = json.load(sys.stdin)
    else:
        with open(path) as f:
            manifest = json.load(f)

    return manifest


def show_validation(result, name):
    if name == "-":
        name = "<stdin>"

    print(f"{BOLD}{name}{RESET} ", end='')

    if result:
        print(f"is {BOLD}{GREEN}valid{RESET}")
        return

    print(f"has {BOLD}{RED}errors{RESET}:")
    print("")

    for error in result:
        print(f"{BOLD}{error.id}{RESET}:")
        print(f"  {error.message}\n")


def parse_arguments(sys_argv):
    parser = argparse.ArgumentParser(description="Build operating system images")

    parser.add_argument("manifest_path", metavar="MANIFEST",
                        help="json file containing the manifest that should be built, or a '-' to read from stdin")
    parser.add_argument("--build-env", metavar="FILE", type=os.path.abspath,
                        help="json file containing a description of the build environment")
    parser.add_argument("--store", metavar="DIRECTORY", type=os.path.abspath,
                        default=".osbuild",
                        help="directory where intermediary os trees are stored")
    parser.add_argument("--sources", metavar="FILE", type=os.path.abspath,
                        help="json file containing a dictionary of source configuration")
    parser.add_argument("--secrets", metavar="FILE", type=os.path.abspath,
                        help="json file containing a dictionary of secrets that are passed to sources")
    parser.add_argument("-l", "--libdir", metavar="DIRECTORY", type=os.path.abspath,
                        help="the directory containing stages, assemblers, and the osbuild library")
    parser.add_argument("--checkpoint", metavar="ID", action="append", type=str, default=None,
                        help="stage to commit to the object store during build (can be passed multiple times)")
    parser.add_argument("--json", action="store_true",
                        help="output results in JSON format")
    parser.add_argument("--output-directory", metavar="DIRECTORY", type=os.path.abspath,
                        help="directory where result objects are stored")

    return parser.parse_args(sys_argv[1:])


def osbuild_cli(*, sys_argv=[]):
    args = parse_arguments(sys_argv)
    manifest = parse_manifest(args.manifest_path)

    # first thing after parsing is validation of the input
    index = osbuild.meta.Index(args.libdir)
    res = osbuild.meta.validate(manifest, index)
    if not res:
        if not args.json:
            show_validation(res, args.manifest_path)
        else:
            json.dump(res.as_dict(), sys.stdout)
            sys.stdout.write("\n")
        return 2

    pipeline = manifest.get("pipeline", {})
    sources_options = manifest.get("sources", {})

    if args.sources:
        with open(args.sources) as f:
            sources_options = json.load(f)

    pipeline = osbuild.load(pipeline, sources_options)

    if args.build_env:
        with open(args.build_env) as f:
            build_pipeline, runner = osbuild.load_build(json.load(f), sources_options)
        pipeline.prepend_build_env(build_pipeline, runner)

    secrets = {}
    if args.secrets:
        with open(args.secrets) as f:
            secrets = json.load(f)

    if args.checkpoint:
        missed = mark_checkpoints(pipeline, args.checkpoint)
        if missed:
            for checkpoint in missed:
                print(f"Checkpoint {BOLD}{checkpoint}{RESET} not found!")
            print(f"{RESET}{BOLD}{RED}Failed{RESET}")
            return 1

    try:
        r = pipeline.run(
            args.store,
            interactive=not args.json,
            libdir=args.libdir,
            secrets=secrets,
            output_directory=args.output_directory
        )
    except KeyboardInterrupt:
        print()
        print(f"{RESET}{BOLD}{RED}Aborted{RESET}")
        return 130

    if args.json:
        json.dump(r, sys.stdout)
        sys.stdout.write("\n")
    else:
        if r["success"]:
            print("tree id:", pipeline.tree_id)
            print("output id:", pipeline.output_id)
        else:
            print()
            print(f"{RESET}{BOLD}{RED}Failed{RESET}")

    return 0 if r["success"] else 1


def main_cli():
    """osbuild-cli entrypoint

    This is the entrypoint used by the `osbuild` executable. We simply fetch the
    global configuration and parameters necessary and invoke the API entrypoint.
    """

    sys.exit(osbuild_cli(sys_argv=sys.argv))
