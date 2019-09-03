import logging
import subprocess
import sys

from .config import *


def run_osbuild(pipeline: str, build_pipeline: str, check=True):
    cmd = OSBUILD + ["--store", OBJECTS, "-o", OUTPUT_DIR, pipeline]
    if build_pipeline:
        cmd += ["--build-pipeline", build_pipeline]
    logging.info(f"Running osbuild: {cmd}")
    osbuild = subprocess.run(cmd, capture_output=False)
    if osbuild.returncode != 0:
        logging.error(f"{RED}osbuild failed!{RESET}")
        print(f"{BOLD}STDERR{RESET}")
        print(osbuild.stderr.decode())
        print(f"{BOLD}STDOUT{RESET}")
        print(osbuild.stdout.decode())
        if check:
            sys.exit(1)

    return osbuild.returncode


def build_testing_image(pipeline_full_path, build_pipeline_full_path):
    run_osbuild(pipeline_full_path, build_pipeline_full_path)
