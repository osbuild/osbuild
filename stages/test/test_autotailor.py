#!/usr/bin/python3

import os.path
import sys
from unittest.mock import call, patch

import pytest

import osbuild.meta
from osbuild import testutil

TEST_INPUT = [
    (
        [
            {"var": "ssh_idle_timeout_value", "value": 60},
        ], [
            "--var-value", "ssh_idle_timeout_value=60",
        ],
    ),
    (
        [
            {"var": "ssh_idle_timeout_value", "value": "60"},
        ], [
            "--var-value", "ssh_idle_timeout_value=60",
        ],
    ),
    (
        [
            {"var": "var1", "value": "val1"},
            {"var": "var2", "value": "val2"}
        ], [
            "--var-value", "var1=val1", "--var-value", "var2=val2",
        ],
    ),
]


STAGE_NAME = "org.osbuild.oscap.autotailor"


@pytest.fixture(name="fake_input")
def fake_input_fixture():
    return {
        "name": STAGE_NAME,
        "options": {
            "filepath": "/some/filepath",
            "config": {
                "profile_id": "some-profile-id",
                "datastream": "some-datastream",
                "new_profile": "some-new-profile",
            }
        },
    }


def schema_validate_stage_oscap_autotailor(fake_input, test_data):
    version = "1"
    root = os.path.join(os.path.dirname(__file__), "../..")
    mod_info = osbuild.meta.ModuleInfo.load(root, "Stage", STAGE_NAME)
    schema = osbuild.meta.Schema(mod_info.get_schema(version=version), STAGE_NAME)
    test_input = fake_input
    test_input["options"]["config"].update(test_data)
    return schema.validate(test_input)


@pytest.mark.parametrize("test_overrides,expected", TEST_INPUT)
@patch("subprocess.run")
def test_oscap_autotailor_overrides_smoke(mock_subprocess_run, fake_input, stage_module, test_overrides, expected):
    options = fake_input["options"]
    options["config"]["overrides"] = test_overrides
    stage_module.main("/some/sysroot", options)

    assert mock_subprocess_run.call_args_list == [
        call(["/usr/bin/autotailor", "--output", "/some/sysroot/some/filepath",
              "--new-profile-id", "some-new-profile"] +
             expected +
             ["some-datastream", "some-profile-id"],
             encoding='utf8', stdout=sys.stderr, check=True)]


@pytest.mark.parametrize(
    "test_data,expected_err",
    [
        ({
            "overrides": [
                {
                    "no": "var",
                    "value": 50,
                },
            ]
        }, "'var' is a required property"),
        ({
            "overrides": [
                {
                    "no": "value",
                    "var": "some",
                },
            ]
        }, "'value' is a required property"),
        ({
            "overrides": [
                {
                    "var": "ssh_idle_timeout_value",
                    "value": {"some": "object"},
                },
            ]
        }, " is not of type 'string', 'integer'"),
    ],
)
def test_schema_validation_oscap_autotailor(fake_input, test_data, expected_err):
    res = schema_validate_stage_oscap_autotailor(fake_input, test_data)

    assert res.valid is False
    testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)
