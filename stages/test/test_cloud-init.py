#!/usr/bin/python3

import os.path

STAGE_NAME = "org.osbuild.cloud-init"


# Test that the 'datasource_list' option is dumped as a single line
# in the configuration file.
def test_cloud_init_datasource_list_single_line(tmp_path, stage_module):
    treedir = tmp_path / "tree"
    confpath = treedir / "etc/cloud/cloud.cfg.d/datasource_list.cfg"
    confpath.parent.mkdir(parents=True, exist_ok=True)

    options = {
        "filename": confpath.name,
        "config": {
            "datasource_list": [
                "Azure",
            ]
        }
    }

    stage_module.main(treedir, options)
    assert os.path.exists(confpath)
    assert confpath.read_text() == "datasource_list: [Azure]\n"
