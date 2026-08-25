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
from typing import List, Optional

import osbuild
import osbuild.meta
import osbuild.monitor
from osbuild.meta import ValidationResult
from osbuild.objectstore import ObjectStore
from osbuild.pipeline import Manifest
from osbuild.util.linux import IdMaps
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
    parser.add_argument("--cache", "--store", metavar="DIRECTORY", type=os.path.abspath,
                        default=".osbuild",
                        help="directory where sources and intermediary os trees are stored")
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
    parser.add_argument("--in-vm", metavar="ID", action="append", type=str, default=[],
                        help="Run a pipeline in a VM")
    parser.add_argument("--json", action="store_true",
                        help="output results in JSON format")
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
    parser.add_argument("--rundir", metavar="DIRECTORY", type=os.path.abspath,
                        default=None,
                        help="directory for temporary runtime data "
                             "(default: /run/osbuild for root, $XDG_RUNTIME_DIR/osbuild otherwise)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="suppress normal output")

    return parser.parse_args(sys_argv[1:])


def _default_rundir() -> str:
    if os.getuid() == 0:
        return "/run/osbuild"
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        return os.path.join(xdg, "osbuild")
    return f"/run/user/{os.getuid()}/osbuild"


def _rootless_container_storage_env() -> dict:
    """Compute CONTAINERS_GRAPHROOT/RUNROOT for the calling (rootless) user.

    Inside the user namespace we appear as uid 0, so c/storage would otherwise
    default to the system-global storage (/var/lib/containers, /run/containers).
    Point it back at the per-user rootless storage instead, just like
    `podman unshare` does, using the rootless c/storage defaults.
    """
    env = {}

    graphroot = os.environ.get("CONTAINERS_GRAPHROOT")
    if not graphroot:
        data_home = os.environ.get("XDG_DATA_HOME") or \
            os.path.join(os.path.expanduser("~"), ".local", "share")
        graphroot = os.path.join(data_home, "containers", "storage")
    env["CONTAINERS_GRAPHROOT"] = graphroot

    runroot = os.environ.get("CONTAINERS_RUNROOT")
    if not runroot:
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        runroot = os.path.join(runtime_dir, "containers")
    env["CONTAINERS_RUNROOT"] = runroot

    return env


def _reexec_in_userns() -> Optional[int]:
    """Re-exec osbuild inside a user namespace with full uid/gid mappings.

    Returns the exit status of the re-exec'd osbuild, for the caller to
    `sys.exit()` with. Returns None if the required support is missing or the
    namespace cannot be set up, so the caller can fall back to the normal code
    path.
    """
    maps = IdMaps.gather()
    if maps is None:
        return None

    argv = sys.argv.copy()
    if argv[0].endswith("__main__.py"):
        argv[:1] = [sys.executable, "-m", "osbuild"]
    if "--rundir" not in argv:
        # Keep the user rundir even though uid will be 0 in the userns
        argv += ["--rundir", _default_rundir()]

    return maps.exec(argv, env=_rootless_container_storage_env())

# pylint: disable=too-many-branches,too-many-return-statements,too-many-statements


def osbuild_cli(no_reexec: bool = False) -> int:
    if not no_reexec and os.getuid() != 0:
        # Re-exec inside a user namespace when running rootless. Do this here in
        # the shared entrypoint (rather than in __main__.py) so it also triggers
        # for the installed `osbuild` console-script, which loads this function
        # directly and never runs __main__.py. Returns the child's exit status,
        # or None to fall through to the normal code path.
        r = _reexec_in_userns()
        if r is not None:
            return r

    args = parse_arguments(sys.argv)
    if args.rundir is None:
        args.rundir = _default_rundir()
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
        available = list(manifest.pipelines.keys())
        for name in unresolved:
            print(f"Export {vt.bold}{name}{vt.reset} not found in {available}")
        print(f"{vt.reset}{vt.bold}{vt.red}Failed{vt.reset}")
        return 1

    if args.checkpoint:
        marked = manifest.mark_checkpoints(args.checkpoint)
        if not marked:
            print("No checkpoints matched provided patterns!")
            print(f"{vt.reset}{vt.bold}{vt.red}Failed{vt.reset}")
            return 1
    else:
        marked = set()

    if args.inspect:
        result = fmt.describe(manifest, with_id=True)
        json.dump(result, sys.stdout)
        sys.stdout.write("\n")
        return 0

    output_directory = args.output_directory

    if exports and not output_directory:
        print("Need --output-directory for --export")
        return 1

    in_vm = set(args.in_vm)

    monitor_name = args.monitor
    if not monitor_name:
        monitor_name = "NullMonitor" if (args.json or args.quiet) else "LogMonitor"

    try:
        with ObjectStore(args.cache) as object_store:
            if args.cache_max_size is not None:
                object_store.maximum_size = args.cache_max_size

            stage_timeout = args.stage_timeout
            debug_break = args.debug_break

            pipelines = manifest.depsolve(object_store, exports)
            total_steps = len(manifest.sources) + len(pipelines)
            monitor = osbuild.monitor.make(monitor_name, args.monitor_fd, total_steps)
            monitor.log(f"starting {args.manifest_path}", origin="osbuild.main_cli")

            r = manifest.build(
                object_store,
                pipelines,
                monitor,
                args.libdir,
                debug_break,
                in_vm=in_vm,
                stage_timeout=stage_timeout,
                rundir=args.rundir
            )
            if r.success:
                monitor.log(f"manifest {args.manifest_path} finished successfully\n", origin="osbuild.main_cli")
            else:
                # if we had monitor.error() we could use that here
                monitor.log(f"manifest {args.manifest_path} failed\n", origin="osbuild.main_cli")

            if r.success and exports:
                for pid in exports:
                    export(pid, output_directory, object_store, manifest)

            if args.json:
                json.dump(fmt.output(manifest, r, object_store), sys.stdout)
                sys.stdout.write("\n")
            elif not args.quiet:
                if r.success:
                    print("\nPipelines")
                    for name, pl in manifest.pipelines.items():
                        print(f"  {name + ':': <10}\t{pl.id}")

                    print("\nCheckpoints")
                    for m in marked:
                        if object_store.contains(m, only_cached=True):
                            print(f"  {m}: cached")
                        else:
                            print(f"  {m}: {vt.reset}{vt.bold}{vt.red}not cached{vt.reset}")
                else:
                    print(f"{vt.reset}{vt.bold}{vt.red}Failed{vt.reset}")

            return 0 if r.success else 1

    except KeyboardInterrupt:
        print()
        print(f"{vt.reset}{vt.bold}{vt.red}Aborted{vt.reset}")
        return 130
