#!/usr/bin/python3

import os.path
import re

import pytest

try:
    import toml
except ModuleNotFoundError:
    import pytoml as toml

import osbuild.meta
from osbuild.testutil import assert_dict_has
from osbuild.testutil.imports import import_module_from_path

TEST_INPUT = [
    ({}, {"additionalimagestores": ["/path/to/store"]}, [("storage.options.additionalimagestores", ["/path/to/store"])]),
    ({}, {"additionalimagestores": ["/path/to/store"]}, [("storage.options.additionalimagestores", ["/path/to/store"])]),
    ({"transient_store": True, "runroot": "/foo"}, {}, [("storage.transient_store", True), ("storage.runroot", '/foo')]),
]


@pytest.mark.parametrize("test_filename", ["/etc/containers/storage.conf", "/usr/share/containers/storage.conf"])
@pytest.mark.parametrize("test_storage,test_options,expected", TEST_INPUT)
def test_containers_storage_conf_integration(tmp_path, test_filename, test_storage, test_options, expected):  # pylint: disable=unused-argument
    treedir = os.path.join(tmp_path, "tree")
    confdir, confname = os.path.split(test_filename.lstrip("/"))
    confdir = os.path.join(treedir, confdir)
    os.makedirs(confdir, exist_ok=True)

    stage_path = os.path.join(os.path.dirname(__file__), "../org.osbuild.containers.storage.conf")
    stage = import_module_from_path("stage", stage_path)
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

    stage.main(treedir, options)

    confpath = os.path.join(confdir, confname)
    assert os.path.exists(confpath)

    conf = None
    with open(confpath, 'r', encoding="utf-8") as f:
        conf = toml.load(f)

    assert conf is not None

    for (key, value) in expected:
        assert_dict_has(conf, key, value)


@pytest.mark.parametrize(
    "test_data,storage_test_data,expected_err",
    [
        # None, note that starting from jsonschema 4.21.0 the error changes
        # so we need a regexp here
        ({}, {}, r"does not have enough properties|should be non-empty"),
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
def test_schema_validation_containers_storage_conf(test_data, storage_test_data, expected_err):
    name = "org.osbuild.containers.storage.conf"
    version = "2"
    root = os.path.join(os.path.dirname(__file__), "../..")
    mod_info = osbuild.meta.ModuleInfo.load(root, "Stage", name)
    schema = osbuild.meta.Schema(mod_info.get_schema(version=version), name)

    test_input = {
        "type": "org.osbuild.containers.storage.conf",
        "options": {
            "config": {
                "storage": {
                }
            }
        }
    }

    test_input["options"].update(test_data)
    test_input["options"]["config"]["storage"].update(storage_test_data)
    res = schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        err_msgs = [e.as_dict()["message"] for e in res.errors]
        assert any(re.search(expected_err, err_msg)
                   for err_msg in err_msgs), f"{expected_err} not found in {err_msgs}"
