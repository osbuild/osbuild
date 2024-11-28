#!/usr/bin/python3

import os
import textwrap

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.containers.unit.create"


@pytest.mark.parametrize("test_data,expected_err", [
    # good
    (
        {
            "filename": "foo.container",
            "config": {
                "Unit": {},
                "Service": {},
                "Container": {
                    "Image": "img"
                },
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "foo.volume",
            "config": {
                "Unit": {},
                "Volume": {},
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "foo.network",
            "config": {
                "Network": {},
            },
        },
        "",
    ),
    # bad
    ({"config": {"Unit": {}, "Container": {"Image": "img"}, "Install": {}}}, "'filename' is a required property"),
    ({"filename": "foo.container"}, "'config' is a required property"),
    ({"filename": "foo.container", "config": {"Container": {"Image": "img"}, "Install": {}}},
     "{'Container': {'Image': 'img'}, 'Install': {}} is not valid under any of the given schemas"),
    ({"filename": "foo.container", "config": {"Unit": {}, "Install": {}}},
     "{'Unit': {}, 'Install': {}} is not valid under any of the given schemas"),
    ({"filename": "foo.container", "config": {"Network": {}, "Volume": {}}},
     "{'Network': {}, 'Volume': {}} is not valid under any of the given schemas")
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
        },
        "",
    ),
    (
        {
            "filename": "foo.network",
            "config": {
                "Unit": {},
                "Network": {},
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "foo.volume",
            "config": {
                "Volume": {},
            },
        },
        "",
    ),
    # bad
    ({"filename": "something.container", "config": {"Unit": {}, "Volume": {}, "Install": {}}},
     "Error: something.container unit requires Container section"),
    ({"filename": "data-gifs-cats.volume", "config": {"Unit": {}, "Network": {}, "Install": {}}},
     "Error: data-gifs-cats.volume unit requires Volume section"),
])
def test_name_config_match(tmp_path, stage_module, test_data, expected_err):
    expected_unit_path = tmp_path / "usr/share/containers/systemd"
    expected_unit_path.mkdir(parents=True, exist_ok=True)
    try:
        stage_module.main(tmp_path, test_data)
    except ValueError as ve:
        assert expected_err == str(ve)


@pytest.mark.parametrize("unit_path,expected_prefix", [
    ("usr", "usr/share/containers/systemd"),
    ("etc", "etc/containers/systemd")
])
def test_systemd_unit_create(tmp_path, stage_module, unit_path, expected_prefix):
    options = {
        "filename": "create-directory.container",
        "unit-path": unit_path,
        "config": {
            "Unit": {
                "Description": "Create directory",
                "DefaultDependencies": False,
                "ConditionPathExists": [
                    "|!/etc/myfile"
                ],
                "ConditionPathIsDirectory": [
                    "|!/etc/mydir"
                ],
                # need to use real units otherwise the validation will fail
                "Wants": [
                    "basic.target",
                    "sysinit.target",
                ],
                "Requires": [
                    "paths.target",
                    "sockets.target",
                ],
                "After": [
                    "sysinit.target",
                    "default.target",
                ],
                "Before": [
                    "multi-user.target",
                ],
            },
            "Container": {
                "Image": "img",
                "Environment": [
                    {
                        "key": "DEBUG",
                        "value": "1",
                    },
                    {
                        "key": "TRACE",
                        "value": "1",
                    },
                ],
                "SecurityLabelFileType": "usr_t",
                "SecurityLabelType": "spc_t",
                "Tmpfs": "/test.tmp",
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

    expected_unit_path = tmp_path / expected_prefix / "create-directory.container"
    expected_unit_path.parent.mkdir(parents=True, exist_ok=True)

    stage_module.main(tmp_path, options)
    assert os.path.exists(expected_unit_path)
    assert expected_unit_path.read_text(encoding="utf-8") == textwrap.dedent("""\
    [Unit]
    Description=Create directory
    DefaultDependencies=False
    ConditionPathExists=|!/etc/myfile
    ConditionPathIsDirectory=|!/etc/mydir
    Wants=basic.target
    Wants=sysinit.target
    Requires=paths.target
    Requires=sockets.target
    After=sysinit.target
    After=default.target
    Before=multi-user.target

    [Container]
    Image=img
    Environment="DEBUG=1"
    Environment="TRACE=1"
    SecurityLabelFileType=usr_t
    SecurityLabelType=spc_t
    Tmpfs=/test.tmp

    [Install]
    WantedBy=local-fs.target
    RequiredBy=multi-user.target

    """)
