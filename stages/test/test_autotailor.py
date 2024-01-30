#!/usr/bin/python3

import sys
from unittest.mock import call, patch

import pytest

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
@pytest.mark.parametrize("stage_schema", ["1"], indirect=True)
def test_schema_validation_oscap_autotailor(fake_input, stage_schema, test_data, expected_err):
    fake_input["options"]["config"].update(test_data)
    res = stage_schema.validate(fake_input)

    assert res.valid is False
    testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)
