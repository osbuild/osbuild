import argparse
import json
import os
import sys
import osbuild


RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"


def main():
    parser = argparse.ArgumentParser(description="Build operating system images")
    parser.add_argument("pipeline_path", metavar="PIPELINE",
                        help="json file containing the pipeline that should be built, or a '-' to read from stdin")
    parser.add_argument("--build-env", metavar="ENV", type=os.path.abspath,
                        help="json file containing a description of the build environment")
    parser.add_argument("--store", metavar="DIRECTORY", type=os.path.abspath,
                        default=".osbuild",
                        help="the directory where intermediary os trees are stored")
    parser.add_argument("-l", "--libdir", metavar="DIRECTORY", type=os.path.abspath,
                        help="the directory containing stages, assemblers, and the osbuild library")
    parser.add_argument("--json", action="store_true",
                        help="output results in JSON format")
    args = parser.parse_args()

    if args.pipeline_path == "-":
        f = sys.stdin
    else:
        f = open(args.pipeline_path)
    pipeline = osbuild.load(json.load(f))
    f.close()

    if args.build_env:
        with open(args.build_env) as f:
            build_pipeline, runner = osbuild.load_build(json.load(f))
        pipeline.prepend_build_env(build_pipeline, runner)

    try:
        pipeline.run(args.store, interactive=not args.json, libdir=args.libdir)
    except KeyboardInterrupt:
        print()
        print(f"{RESET}{BOLD}{RED}Aborted{RESET}")
        return 130
    except (osbuild.StageFailed, osbuild.AssemblerFailed) as error:
        print()
        print(f"{RESET}{BOLD}{RED}{error.name} failed with code {error.returncode}{RESET}")
        if args.json:
            print(error.output)
        return 1

    if args.json:
        json.dump({
            "tree_id": pipeline.tree_id,
            "output_id": pipeline.output_id,
        }, sys.stdout)
        sys.stdout.write("\n")
    else:
        print("tree id:", pipeline.tree_id)
        print("output id:", pipeline.output_id)

    return 0


if __name__ == "__main__":
    sys.exit(main())
