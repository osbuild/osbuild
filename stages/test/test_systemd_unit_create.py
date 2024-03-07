#!/usr/bin/python3

import os
import os.path
import textwrap

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.systemd.unit.create"


@pytest.mark.parametrize("test_data,expected_err", [
    # good
    (
        {
            "filename": "foo.service",
            "config": {
                "Unit": {},
                "Service": {},
                "Install": {},
            },
        }, ""),
    # bad
    ({"config": {"Unit": {}, "Service": {}, "Install": {}}}, "'filename' is a required property"),
    ({"filename": "foo.service"}, "'config' is a required property"),
    ({"filename": "foo.service", "config": {"Service": {}, "Install": {}}},
     "'Unit' is a required property"),
    ({"filename": "foo.service", "config": {"Unit": {}, "Install": {}}},
     "'Service' is a required property"),
    ({"filename": "foo.service", "config": {"Unit": {}, "Service": {}}},
     "'Install' is a required property"),
])
@pytest.mark.parametrize("stage_schema", ["1"], indirect=True)
def test_schema_validation(stage_schema, test_data, expected_err):
    test_input = {
        "name": STAGE_NAME,
        "options": test_data,
    }
    res = stage_schema.validate(test_input)
    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


@pytest.mark.parametrize("unit_type,unit_path,expected_prefix", [
    ("system", "usr", "usr/lib/systemd/system"),
    ("system", "etc", "etc/systemd/system"),
    ("global", "usr", "usr/lib/systemd/user"),
    ("global", "etc", "etc/systemd/user"),
])
def test_systemd_unit_create(tmp_path, stage_module, unit_type, unit_path, expected_prefix):
    options = {
        "filename": "create-directory.service",
        "unit-type": unit_type,
        "unit-path": unit_path,
        "config": {
            "Unit": {
                "Description": "Create directory",
                "DefaultDependencies": False,
                "ConditionPathExists": [
                    "|!/etc/myfile"
                ]
            },
            "Service": {
                "Type": "oneshot",
                "RemainAfterExit": True,
                "ExecStart": [
                    "mkdir -p /etc/mydir",
                    "touch /etc/myfile"
                ]
            },
            "Install": {
                "WantedBy": [
                    "local-fs.target"
                ],
                "RequiredBy": [
                    "multi-user.target"
                ]
            }
        }
    }
    expected_unit_path = tmp_path / expected_prefix / "create-directory.service"
    # should the stage create the dir?
    expected_unit_path.parent.mkdir(parents=True)

    stage_module.main(tmp_path, options)
    assert os.path.exists(expected_unit_path)
    assert expected_unit_path.read_text(encoding="utf-8") == textwrap.dedent("""\
    [Unit]
    Description=Create directory
    DefaultDependencies=False
    ConditionPathExists=|!/etc/myfile

    [Service]
    Type=oneshot
    RemainAfterExit=True
    ExecStart=mkdir -p /etc/mydir
    ExecStart=touch /etc/myfile

    [Install]
    WantedBy=local-fs.target
    RequiredBy=multi-user.target

    """)
