
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


class TestCase(unittest.TestCase):
    """A TestCase to test running the osbuild program.

    Each test case can use `self.run_osbuild()` to run osbuild. A temporary
    store is used, which can be accessed through `self.store`.

    To speed up local development, OSBUILD_TEST_STORE can be set to an existing
    store. Note that this might make tests dependant of each other. Do not use
    it for actual testing.
    """

    def setUp(self):
        self.store = os.getenv("OSBUILD_TEST_STORE")
        if not self.store:
            self.store = tempfile.mkdtemp(dir="/var/tmp")

    def tearDown(self):
        if not os.getenv("OSBUILD_TEST_STORE"):
            shutil.rmtree(self.store)

    def run_osbuild(self, pipeline):
            osbuild_cmd = ["python3", "-m", "osbuild", "--json", "--store", self.store, "--libdir", ".", pipeline]

            build_pipeline = os.getenv("OSBUILD_TEST_BUILD_PIPELINE", None)
            if build_pipeline:
                osbuild_cmd.append("--build-pipeline")
                osbuild_cmd.append(build_pipeline)

            r = subprocess.run(osbuild_cmd, encoding="utf-8", stdout=subprocess.PIPE, check=True)

            result = json.loads(r.stdout)
            return result["tree_id"], result["output_id"]
