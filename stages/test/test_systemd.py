#!/usr/bin/python3

import os
import os.path

from osbuild.testutil.imports import import_module_from_path


def test_systemd_masked_generators(tmp_path):
    stage_path = os.path.join(os.path.dirname(__file__), "../org.osbuild.systemd")
    stage = import_module_from_path("stage", stage_path)

    options = {"masked_generators": ["fake-generator"]}

    stage.main(tmp_path, options)

    masked_generator_path = os.path.join(tmp_path, "etc/systemd/system-generators/fake-generator")
    assert os.path.lexists(masked_generator_path)
    assert os.readlink(masked_generator_path) == "/dev/null"
