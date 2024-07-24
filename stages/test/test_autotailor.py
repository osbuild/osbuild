#!/usr/bin/python3

import subprocess
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
                "tailored_profile_id": "some-new-profile",
            }
        },
    }


@pytest.fixture(name="fake_json_input")
def fake_json_input_fixture():
    return {
        "name": STAGE_NAME,
        "options": {
            "filepath": "tailoring-output.xml",
            "config": {
                "datastream": "some-datastream",
                "tailored_profile_id": "some-new-profile",
                "tailoring_file": "tailoring-file.json",
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
        }, "{'profile_id': 'some-profile-id', 'datastream': 'some-datastream', 'tailored_profile_id': 'some-new-profile',"
            + " 'overrides': [{'no': 'var', 'value': 50}]} is not valid under any of the given schemas"),
        ({
            "overrides": [
                {
                    "no": "value",
                    "var": "some",
                },
            ]
        }, "{'profile_id': 'some-profile-id', 'datastream': 'some-datastream', 'tailored_profile_id': 'some-new-profile',"
            + " 'overrides': [{'no': 'value', 'var': 'some'}]} is not valid under any of the given schemas"),
        ({
            "overrides": [
                {
                    "var": "ssh_idle_timeout_value",
                    "value": {"some": "object"},
                },
            ]
        }, "{'profile_id': 'some-profile-id', 'datastream': 'some-datastream', 'tailored_profile_id': 'some-new-profile',"
            + " 'overrides': [{'var': 'ssh_idle_timeout_value', 'value': {'some': 'object'}}]} is not valid under any of the given schemas"),
    ],
)
@pytest.mark.parametrize("stage_schema", ["1"], indirect=True)
def test_schema_validation_oscap_autotailor(fake_input, stage_schema, test_data, expected_err):
    fake_input["options"]["config"].update(test_data)
    res = stage_schema.validate(fake_input)

    assert res.valid is False
    testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


@patch("subprocess.run")
def test_oscap_autotailor_json_smoke(mock_subprocess_run, fake_json_input, stage_module):
    options = fake_json_input["options"]
    stage_module.main("/some/sysroot", options)

    assert mock_subprocess_run.call_args_list == [
        call(["/usr/bin/autotailor", "--output", "/some/sysroot/tailoring-output.xml",
              "--new-profile-id", "some-new-profile",
              "--json-tailoring", "/some/sysroot/tailoring-file.json", "some-datastream"],
             encoding='utf8', stdout=sys.stderr, check=True)]


@pytest.mark.parametrize(
    "test_data,expected_err",
    [
        ({}, "{} is not valid under any of the given schemas"),
        ({
            "tailored_profile_id": "some-new-profile"
        }, "{'tailored_profile_id': 'some-new-profile'}"
            + " is not valid under any of the given schemas"),
        ({
            "datastream": "some-datastream",
            "tailored_profile_id": "some-new-profile"
        }, "{'datastream': 'some-datastream', 'tailored_profile_id': 'some-new-profile'}"
            + " is not valid under any of the given schemas"),
        ({
            "datastream": "some-datastream",
            "profile_id": "some-profile-id",
        }, "{'datastream': 'some-datastream', 'profile_id': 'some-profile-id'}"
            + " is not valid under any of the given schemas"),
        ({
            "datastream": "some-datastream",
            "tailoring_file": "/some/tailoring/file.json"
        }, "{'datastream': 'some-datastream', 'tailoring_file': '/some/tailoring/file.json'}"
            + " is not valid under any of the given schemas"),
    ],
)
@pytest.mark.parametrize("stage_schema", ["1"], indirect=True)
def test_schema_validation_oscap_json_autotailor(fake_json_input, stage_schema, test_data, expected_err):
    fake_json_input["options"]["config"] = test_data
    res = stage_schema.validate(fake_json_input)
    assert res.valid is False
    testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


JSON_TAILORING = """{
  "profiles": [
    {
      "id": "some-profile-id",
      "base_profile_id": "some-profile-id",
      "rules": {
        "some-rule": {
          "evaluate": true,
          "severity": "high"
        }
      },
      "variables": {
        "some-variable": {
          "value": 600
        }
      }
    }
  ]
}
"""


@pytest.mark.parametrize(
    "expected_profile",
    [
        ("xccdf_org.ssgproject.content_profile_some-new-profile"),
        ("xccdf_org.ssgproject.content_profile_some-other-profile")
    ]
)
@pytest.mark.skipif(not testutil.has_executable("autotailor"), reason="no autotailor executable")
def test_oscap_autotailor_json_profile_override(fake_json_input, stage_module, expected_profile, tmp_path):
    options = fake_json_input["options"]
    options["config"]["tailored_profile_id"] = expected_profile

    results_file = tmp_path / options["filepath"]
    tailoring_file = tmp_path / options["config"]["tailoring_file"]
    tailoring_file.write_text(JSON_TAILORING)

    stage_module.main(str(tmp_path), options)

    result = subprocess.run(
        ["oscap", "info", "--profiles", results_file],
        stdout=subprocess.PIPE,
        check=True,
        text=True,
    )

    assert f"Id: {expected_profile}\n" in result.stdout
