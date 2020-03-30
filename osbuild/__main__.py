import argparse
import json
import os
import sys
import osbuild


RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"


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


# pylint: disable=too-many-branches
# pylint: disable=too-many-statements
def main():
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
    args = parser.parse_args()

    if args.manifest_path == "-":
        f = sys.stdin
    else:
        f = open(args.manifest_path)
    manifest = json.load(f)
    f.close()

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
            secrets=secrets
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


if __name__ == "__main__":
    sys.exit(main())
