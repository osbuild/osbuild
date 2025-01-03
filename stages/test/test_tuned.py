#!/usr/bin/python3

import re

import pytest

from osbuild.testutil import (
    assert_jsonschema_error_contains,
    make_fake_tree,
)

STAGE_NAME = "org.osbuild.tuned"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({"profiles": {}}, r"{} is not of type 'array'"),
    ({"profiles": ""}, r"'' is not of type 'array'"),
    ({"profiles": []}, r"(\[\] is too short|\[\] should be non-empty)"),
    ({"profiles": [0]}, r"0 is not of type 'string'"),
    ({"profiles": [""]}, r"('' is too short|'' should be non-empty)"),
    ({}, r"'profiles' is a required property"),
    # good
    ({"profiles": ["balanced"]}, ""),
    ({"profiles": ["balanced", "sap-hana"]}, ""),
])
def test_schema_validation(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": {},
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        assert_jsonschema_error_contains(res, re.compile(expected_err), expected_num_errs=1)


@pytest.mark.parametrize("fake_tree,available_profiles", (
    ({}, []),
    # simple case with just installed profiles
    (
        {
            "/usr/lib/tuned/balanced/tuned.conf": "",
            "/usr/lib/tuned/sap/tuned.conf": ""
        },
        ["balanced", "sap"]
    ),
    # simple case with installed and custom profiles
    (
        {
            "/usr/lib/tuned/balanced/tuned.conf": "",
            "/usr/lib/tuned/sap/tuned.conf": "",
            "/etc/tuned/custom/tuned.conf": ""
        },
        ["balanced", "sap", "custom"]
    ),
    # Tuned 2.23.0+ with profiles under profiles/ directory
    # in which case we ignore profiles not under profiles/
    (
        {
            "/usr/lib/tuned/profiles/balanced/tuned.conf": "",
            "/usr/lib/tuned/sap/tuned.conf": ""
        },
        ["balanced"]
    ),
    (
        {
            "/usr/lib/tuned/profiles/balanced/tuned.conf": "",
            "/etc/tuned/sap/tuned.conf": ""
        },
        ["balanced", "sap"]
    ),
    (
        {
            "/usr/lib/tuned/profiles/balanced/tuned.conf": "",
            "/etc/tuned/profiles/sap/tuned.conf": ""
        },
        ["balanced", "sap"]
    ),
    (
        {
            "/etc/tuned/profiles/balanced/tuned.conf": "",
            "/etc/tuned/sap/tuned.conf": ""
        },
        ["balanced"]
    ),
    (
        {
            "/usr/lib/tuned/profiles/profile1/tuned.conf": "",
            "/usr/lib/tuned/profiles/profile2/tuned.conf": "",
            "/usr/lib/tuned/profile3/tuned.conf": "",
            "/etc/tuned/profiles/profile11/tuned.conf": "",
            "/etc/tuned/profiles/profile12/tuned.conf": "",
            "/etc/tuned/profile13/tuned.conf": "",
        },
        ["profile1", "profile2", "profile11", "profile12"]
    ),
))
def test_tunedprofilesdb__load_available_profiles(tmp_path, stage_module, fake_tree, available_profiles):
    make_fake_tree(tmp_path, fake_tree)
    # pylint: disable=protected-access
    assert sorted(stage_module.TunedProfilesDB._load_available_profiles(tmp_path)) == sorted(available_profiles)


def test_tuned_happy(tmp_path, stage_module):
    make_fake_tree(tmp_path, {
        "/usr/lib/tuned/balanced/tuned.conf": "",
        "/usr/lib/tuned/sap/tuned.conf": "",
        "/etc/tuned/custom/tuned.conf": "",
    })

    options = {
        "profiles": ["balanced", "sap", "custom"]
    }

    assert stage_module.main(tmp_path.as_posix(), options) == 0

    active_profile_file = tmp_path / "etc/tuned/active_profile"
    assert active_profile_file.is_file()
    assert active_profile_file.read_text() == "balanced sap custom\n"

    profile_mode_file = tmp_path / "etc/tuned/profile_mode"
    assert profile_mode_file.is_file()
    assert profile_mode_file.read_text() == "manual\n"


def test_tuned_unhappy(tmp_path, stage_module):
    make_fake_tree(tmp_path, {
        "/usr/lib/tuned/balanced/tuned.conf": "",
        "/usr/lib/tuned/sap/tuned.conf": "",
        "/etc/tuned/custom/tuned.conf": "",
    })

    options = {
        "profiles": ["balanced", "non-existing"]
    }

    try:
        stage_module.main(tmp_path.as_posix(), options)
    except ValueError as e:
        assert "non-existing" in str(e)
    else:
        assert False, "Exception not raised"

    active_profile_file = tmp_path / "etc/tuned/active_profile"
    assert not active_profile_file.exists()

    profile_mode_file = tmp_path / "etc/tuned/profile_mode"
    assert not profile_mode_file.exists()
