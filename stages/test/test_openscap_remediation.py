#!/usr/bin/python3

import os
import subprocess
import sys
from unittest.mock import MagicMock, call, patch

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.oscap.remediation"

TEST_INPUT = [
    (
        {"datastream": "some-datastream", "profile_id": "some-profile-id"},
        "some-datastream",
        "some-profile-id",
        None,
    ),
    (
        {"datastream": "some-datastream", "profile_id": "some-profile-id", "tailoring": "/some/tailoring-file.xml"},
        "some-datastream",
        "some-profile-id",
        "/some/tailoring-file.xml",
    )
]


@pytest.fixture(name="fake_input")
def fake_input_fixture():
    return {
        "type": STAGE_NAME,
        "options": {
            "data_dir": "/some/data/dir",
            "config": {}
        },
    }


@pytest.mark.parametrize(
    "test_data,expected_err",
    [
        ({"profile_id": "some-profile-id"}, "'datastream' is a required property"),
        ({"datastream": "some-datastream"}, "'profile_id' is a required property"),
    ],
)
def test_schema_validation_oscap_remediation(fake_input, stage_schema, test_data, expected_err):
    fake_input["options"]["config"].update(test_data)

    res = stage_schema.validate(fake_input)

    assert res.valid is False
    testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


@pytest.mark.skipif(not testutil.has_executable("oscap"), reason="no oscap executable")
@pytest.mark.parametrize("test_input,expected_datastream,expected_profile,expected_tailoring_file", TEST_INPUT)
@patch("os.symlink")
@patch("osbuild.util.mnt.mount")
@patch("subprocess.run")
def test_oscap_remediaton_smoke(
    mock_run,
    mock_mount,
    _,
    fake_input,
    stage_module,
    test_input,
    expected_datastream,
    expected_profile,
    expected_tailoring_file,
):
    options = fake_input["options"]
    options["config"] = test_input

    # we mount /dev & /proc, so we need to fake this
    mock_mount.side_effect = [None, None]

    def fake_subprocess_call():
        m = MagicMock()
        m.returncode = 0
        return m

    # the openscap remediation stage makes 3 subprocess calls,
    # the first one evaluates the tree, the second generates
    # the remediation script and the third executes the script.
    # In each phase, the return code and results are checked
    subprocess_calls = [
        fake_subprocess_call(),
        fake_subprocess_call(),
        fake_subprocess_call(),
    ]

    mock_run.side_effect = subprocess_calls

    result = stage_module.main("/some/sysroot", options)

    assert mock_mount.call_count == 2

    tailoring_opts = []
    if expected_tailoring_file is not None:
        tailoring_opts.extend(["--tailoring-file", expected_tailoring_file])

    chroot = ["/usr/sbin/chroot", "/some/sysroot"]
    expected_calls = [
        call(
            chroot + [
                "/usr/bin/oscap",
                "xccdf", "eval",
                "--profile", expected_profile,
            ] + tailoring_opts +
            [
                "--results", "some/data/dir/oscap_eval_xccdf_results.xml",
                expected_datastream,
            ],
            encoding="utf8",
            stdout=sys.stderr,
            check=False,
            env=dict(os.environ, OSCAP_PROBE_ROOT="", OSCAP_CONTAINER_VARS="container=bwrap-osbuild"),
        ),
        call(
            chroot + [
                "/usr/bin/oscap",
                "xccdf", "generate", "fix",
                "--profile", expected_profile,
            ] + tailoring_opts +
            [
                "--fix-type", "bash",
                "--output", "some/data/dir/oscap_remediation.bash",
                "some/data/dir/oscap_eval_xccdf_results.xml",
            ],
            encoding="utf8",
            stdout=sys.stderr,
            check=False,
        ),
        call(
            chroot +
            [
                "/usr/bin/bash",
                "some/data/dir/oscap_remediation.bash",
            ],
            encoding="utf8",
            stdout=sys.stderr,
            stderr=None,
            check=False,
        ),
    ]

    assert mock_run.call_count == len(expected_calls)
    assert mock_run.call_args_list == expected_calls
    assert result == 0
