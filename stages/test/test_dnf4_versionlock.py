#!/usr/bin/python3
import os

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.dnf4.versionlock"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({}, "'add' is a required property"),
    # good
    ({"add": ["shim-x64-*"]}, ""),
    ({"add": ["proto-1:1.1", "deftero-0:2.2", "trito-3:3.3-3.fc33"]}, ""),
])
def test_schema_validation_dnf4_versionlock(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": test_data
    }
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


@pytest.mark.parametrize("test_data", [
    ({"add": ["shim-x64-*"]}),
    ({"add": ["proto-1:1.1", "deftero-0:2.2", "trito-3:3.3-3.fc33"]}),
])
def test_locklist_dnf4_versionlock(tmp_path, stage_module, test_data):
    os.environ["SOURCE_DATE_EPOCH"] = "1554721380"
    plugins_dir = os.path.join(tmp_path, "etc/dnf/plugins/")
    locklist_path = os.path.join(plugins_dir, "versionlock.list")
    os.makedirs(plugins_dir)
    stage_module.main(tmp_path, test_data)

    with open(locklist_path, mode="r", encoding="utf-8") as locklist_fp:
        locklist_data = locklist_fp.readlines()

    for idx, package in enumerate(test_data["add"]):
        assert locklist_data[idx * 3] == "\n"
        assert locklist_data[idx * 3 + 1] == "# Added lock on Mon Apr  8 11:03:00 2019\n"
        assert locklist_data[idx * 3 + 2] == package + "\n"
