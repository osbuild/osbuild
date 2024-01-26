#!/usr/bin/python3

import os.path

from osbuild.testutil.imports import import_module_from_path


# Test that the 'datasource_list' option is dumped as a single line
# in the configuration file.
def test_cloud_init_datasource_list_single_line(tmp_path):
    treedir = tmp_path / "tree"
    confpath = treedir / "etc/cloud/cloud.cfg.d/datasource_list.cfg"
    confpath.parent.mkdir(parents=True, exist_ok=True)

    stage_path = os.path.join(os.path.dirname(__file__), "../org.osbuild.cloud-init")
    stage = import_module_from_path("stage", stage_path)

    options = {
        "filename": confpath.name,
        "config": {
            "datasource_list": [
                "Azure",
            ]
        }
    }

    stage.main(treedir, options)
    assert os.path.exists(confpath)
    assert confpath.read_text() == "datasource_list: [Azure]\n"
