
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


class TestCase(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(dir="/var/tmp")

    def tearDown(self):
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
