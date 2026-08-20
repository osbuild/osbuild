#!/usr/bin/python3

import os

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.os-release"


@pytest.mark.parametrize("test_data,expected_errs", [
    # minimal
    (
        {"vars": {"ID": "fedora"}},
        "",
    ),
    # full
    (
        {
            "vars": {
                "NAME": "Fedora Linux",
                "ID": "fedora",
                "VERSION": "40 (Workstation Edition)",
                "VERSION_ID": "40",
                "PRETTY_NAME": "Fedora Linux 40 (Workstation Edition)",
                "VARIANT": "Workstation Edition",
                "VARIANT_ID": "workstation",
                "PLATFORM_ID": "platform:f40",
                "HOME_URL": "https://fedoraproject.org/",
                "BUG_REPORT_URL": "https://bugzilla.redhat.com/",
            },
        },
        "",
    ),
    # custom path
    (
        {"path": "usr/lib/initrd-release", "vars": {"ID": "fedora"}},
        "",
    ),
    # empty vars (bad)
    (
        {"vars": {}},
        "",
    ),
    # missing vars (bad)
    (
        {},
        "'vars' is a required property",
    ),
    # bad ID pattern
    (
        {"vars": {"ID": "INVALID UPPER"}},
        "'INVALID UPPER' does not match",
    ),
    # bad VERSION_ID pattern
    (
        {"vars": {"VERSION_ID": "NOT VALID"}},
        "'NOT VALID' does not match",
    ),
    # bad VERSION_CODENAME pattern
    (
        {"vars": {"VERSION_CODENAME": "NOT VALID"}},
        "'NOT VALID' does not match",
    ),
    # bad VARIANT_ID pattern
    (
        {"vars": {"VARIANT_ID": "NOT VALID"}},
        "'NOT VALID' does not match",
    ),
    # bad IMAGE_ID pattern
    (
        {"vars": {"IMAGE_ID": "NOT VALID"}},
        "'NOT VALID' does not match",
    ),
    # bad IMAGE_VERSION pattern
    (
        {"vars": {"IMAGE_VERSION": "NOT VALID"}},
        "'NOT VALID' does not match",
    ),
    # bad ID_LIKE pattern
    (
        {"vars": {"ID_LIKE": "UPPER"}},
        "'UPPER' does not match",
    ),
    # valid ID_LIKE with spaces
    (
        {"vars": {"ID_LIKE": "rhel fedora"}},
        "",
    ),
    # extension-release fields
    (
        {
            "vars": {
                "ID": "fedora",
                "EXTENSION_RELOAD_MANAGER": "1",
                "PORTABLE_SCOPE": "system",
                "RELEASE_TYPE": "stable",
            },
        },
        "",
    ),
    # bad EXTENSION_RELOAD_MANAGER value
    (
        {"vars": {"EXTENSION_RELOAD_MANAGER": "0"}},
        "'0' is not one of",
    ),
    # bad PORTABLE_SCOPE value
    (
        {"vars": {"PORTABLE_SCOPE": "invalid"}},
        "'invalid' is not one of",
    ),
    # bad RELEASE_TYPE value
    (
        {"vars": {"RELEASE_TYPE": "invalid"}},
        "'invalid' is not one of",
    ),
    # SYSEXT_ prefixed variables
    (
        {
            "vars": {
                "ID": "fedora",
                "SYSEXT_ID": "myext",
                "SYSEXT_VERSION_ID": "1.0",
            },
        },
        "",
    ),
    # unknown variable (bad)
    (
        {"vars": {"UNKNOWN_VAR": "value"}},
        "does not match any of the regexes",
    ),
])
@pytest.mark.parametrize("stage_schema", ["1"], indirect=True)
def test_schema_validation(stage_schema, test_data, expected_errs):
    test_input = {
        "name": STAGE_NAME,
        "options": test_data,
    }
    res = stage_schema.validate(test_input)
    if expected_errs == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_errs)


@pytest.mark.parametrize("options,expected_lines", [
    (
        {"vars": {"NAME": "Fedora Linux", "ID": "fedora", "VERSION_ID": "40"}},
        ['NAME="Fedora Linux"', "ID=fedora", "VERSION_ID=40"],
    ),
    (
        {
            "vars": {
                "NAME": "Red Hat Enterprise Linux",
                "VERSION": "8.2 (Ootpa)",
                "ID": "rhel",
                "ID_LIKE": "fedora",
            },
        },
        [
            'NAME="Red Hat Enterprise Linux"',
            'VERSION="8.2 (Ootpa)"',
            "ID=rhel",
            "ID_LIKE=fedora",
        ],
    ),
    # custom path
    (
        {"path": "etc/os-release", "vars": {"ID": "fedora"}},
        ["ID=fedora"],
    ),
])
def test_os_release_contents(tmp_path, stage_module, options, expected_lines):
    stage_module.main(tmp_path, options)

    path = options.get("path", "usr/lib/os-release")
    filepath = os.path.join(tmp_path, path)
    assert os.path.exists(filepath)

    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    for line in expected_lines:
        assert line in content


def test_os_release_default_path(tmp_path, stage_module):
    stage_module.main(tmp_path, {"vars": {"ID": "test"}})
    assert os.path.exists(os.path.join(tmp_path, "usr", "lib", "os-release"))


def test_os_release_creates_intermediate_dirs(tmp_path, stage_module):
    stage_module.main(tmp_path, {"path": "some/deep/nested/dir/os-release", "vars": {"ID": "test"}})
    filepath = os.path.join(tmp_path, "some", "deep", "nested", "dir", "os-release")
    assert os.path.exists(filepath)


def test_extension_release_strict_false(tmp_path, stage_module):
    options = {"extension-release-strict": False, "vars": {"ID": "fedora"}}
    stage_module.main(tmp_path, options)
    filepath = os.path.join(tmp_path, "usr", "lib", "os-release")
    xattr = os.getxattr(filepath, "user.extension-release.strict")
    assert xattr == b"0"


def test_extension_release_strict_default(tmp_path, stage_module):
    stage_module.main(tmp_path, {"vars": {"ID": "fedora"}})
    filepath = os.path.join(tmp_path, "usr", "lib", "os-release")
    with pytest.raises(OSError):
        os.getxattr(filepath, "user.extension-release.strict")


def test_format_value_quoting(stage_module):
    assert stage_module.format_value("simple") == "simple"
    assert stage_module.format_value("has space") == '"has space"'
    assert stage_module.format_value('has"quote') == '"has\\"quote"'
    assert stage_module.format_value("has$dollar") == '"has\\$dollar"'
    assert stage_module.format_value("has`backtick") == '"has\\`backtick"'
