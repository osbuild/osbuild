#!/usr/bin/python3

import os.path
import re

import pytest

from osbuild import testutil
from osbuild.util import toml

TEST_INPUT = [
    ({}, {"additionalimagestores": ["/path/to/store"]}, [("storage.options.additionalimagestores", ["/path/to/store"])]),
    ({}, {"additionalimagestores": ["/path/to/store"]}, [("storage.options.additionalimagestores", ["/path/to/store"])]),
    ({"transient_store": True, "runroot": "/foo"}, {}, [("storage.transient_store", True), ("storage.runroot", '/foo')]),
]


STAGE_NAME = "org.osbuild.containers.storage.conf"


@pytest.mark.parametrize("test_filename", ["/etc/containers/storage.conf", "/usr/share/containers/storage.conf"])
@pytest.mark.parametrize("test_storage,test_options,expected", TEST_INPUT)
def test_containers_storage_conf_integration(tmp_path, stage_module, test_filename, test_storage, test_options, expected):  # pylint: disable=unused-argument
    treedir = os.path.join(tmp_path, "tree")
    confdir, confname = os.path.split(test_filename.lstrip("/"))
    confdir = os.path.join(treedir, confdir)
    os.makedirs(confdir, exist_ok=True)

    options = {
        "filename": test_filename,
        "config": {
            "storage": {
                "options": {
                }
            }
        }
    }

    options["config"]["storage"].update(test_storage)
    options["config"]["storage"]["options"].update(test_options)

    stage_module.main(treedir, options)

    confpath = os.path.join(confdir, confname)
    assert os.path.exists(confpath)

    conf = None
    conf = toml.load_from_file(confpath)

    assert conf is not None

    for (key, value) in expected:
        testutil.assert_dict_has(conf, key, value)


@pytest.mark.parametrize(
    "test_data,storage_test_data,expected_err",
    [
        # None, note that starting from jsonschema 4.21.0 the error changes
        # so we need a regexp here
        ({}, {}, re.compile("does not have enough properties|should be non-empty")),
        # All options
        ({
            "filename": "/etc/containers/storage.conf",
            "filebase": "/some/path",
            "comment": ["List of", "comments"]
        },
            {
            "driver": "vfs",
            "graphroot": "/some/path",
            "runroot": "/other/path",
            "transient_store": True,
            "options": {
                "additionalimagestores": ["/path/to/store"],
                "pull_options": {
                    "enable_partial_images": "true",
                    "use_hard_links": "false",
                    "convert_images": "false"
                },
                "overlay": {
                    "mountopt": "metadata"
                }
            }
        }, ""),
        ({}, {"transient_store": "true"}, "is not of type 'boolean'"),
        # Pull options are strings, not booleans (in the config file format)
        ({}, {"options": {"pull_options": {"use_hard_links": "foobar"}}}, "is not one of"),
        ({}, {"options": {"pull_options": {"use_hard_links": True}}}, "is not one of"),
        ({}, {"options": {"pull_options": {"use_hard_links": True}}}, "is not of type 'string'"),
    ],
)
def test_schema_validation_containers_storage_conf(stage_schema, test_data, storage_test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": {
            "config": {
                "storage": {
                }
            }
        }
    }

    test_input["options"].update(test_data)
    test_input["options"]["config"]["storage"].update(storage_test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err)
