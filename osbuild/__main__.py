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
                        help="json file containing the pipeline that should be built")
    parser.add_argument("--build-pipeline", metavar="PIPELINE", type=os.path.abspath,
                        help="json file containing the pipeline to create a build environment")
    parser.add_argument("--store", metavar="DIRECTORY", type=os.path.abspath,
                        default=".osbuild",
                        help="the directory where intermediary os trees are stored")
    parser.add_argument("-l", "--libdir", metavar="DIRECTORY", type=os.path.abspath,
                        help="the directory containing stages, assemblers, and the osbuild library")
    parser.add_argument("--json", action="store_true",
                        help="output results in JSON format")
    requiredNamed = parser.add_argument_group('required named arguments')
    requiredNamed.add_argument("-o", "--output", dest="output_dir", metavar="DIRECTORY", type=os.path.abspath,
                               help="provide the empty DIRECTORY as output argument to the last stage", required=True)
    args = parser.parse_args()

    with open(args.pipeline_path) as f:
        pipeline = osbuild.load(json.load(f))

    if args.build_pipeline:
        with open(args.build_pipeline) as f:
            build = osbuild.load(json.load(f))
        pipeline.prepend_build_pipeline(build)

    try:
        pipeline.run(args.output_dir, args.store, interactive=not args.json, libdir=args.libdir)
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
