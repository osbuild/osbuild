#!/usr/bin/python3

import os
import os.path

STAGE_NAME = "org.osbuild.systemd"


def test_systemd_masked_generators(tmp_path, stage_module):
    options = {"masked_generators": ["fake-generator"]}

    stage_module.main(tmp_path, options)

    masked_generator_path = os.path.join(tmp_path, "etc/systemd/system-generators/fake-generator")
    assert os.path.lexists(masked_generator_path)
    assert os.readlink(masked_generator_path) == "/dev/null"
