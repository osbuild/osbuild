import json
import os
import shutil
import subprocess
import tempfile
import unittest


class TestCase(unittest.TestCase):
    """A TestCase to test running the osbuild program.

    Each test case can use `self.run_osbuild()` to run osbuild. A temporary
    store is used, which can be accessed through `self.store`.
    """

    def setUp(self):
        self.store = tempfile.mkdtemp(dir="/var/tmp")

    def tearDown(self):
        shutil.rmtree(self.store)

    def run_osbuild(self, pipeline, input=None):
        osbuild_cmd = ["python3", "-m", "osbuild", "--json", "--store", self.store, "--libdir", ".", pipeline]

        build_pipeline = os.getenv("OSBUILD_TEST_BUILD_PIPELINE", None)
        if build_pipeline:
            osbuild_cmd.append("--build-pipeline")
            osbuild_cmd.append(build_pipeline)

        try:
            r = subprocess.run(osbuild_cmd, encoding="utf-8", input=input, stdout=subprocess.PIPE, check=True)
        except subprocess.CalledProcessError as e:
            print(e.stdout)
            raise e from None

        result = json.loads(r.stdout)
        return result["tree_id"], result["output_id"]
