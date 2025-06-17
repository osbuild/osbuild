#!/usr/bin/python3

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.wsl-distribution.conf"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({"oobe": "must-be-object"}, "'must-be-object' is not of type 'object'"),
    ({"shortcut": "must-be-object"}, "'must-be-object' is not of type 'object'"),
    ({"shortcut": {"enabled": 1}}, "1 is not of type 'boolean'"),
    ({"oobe": {"default_uid": True}}, "True is not of type 'integer'"),
    # good
    ({
        "oobe":
        {
            "default_uid": 1000,
            "default_name": "RedHatEnterpriseLinux-10.0",
        },
        "shortcut":
        {
            "enabled": True,
            "icon": "/usr/share/pixmaps/fedora-logo.ico",
        }
    }, "")
])
def test_wsl_distribution_conf_schema_validation(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": {
        }
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


def test_wsl_distribution_conf_writes_file(tmp_path, stage_module):
    treepath = tmp_path / "tree"

    etcpath = treepath / "etc"
    etcpath.mkdir(parents=True, exist_ok=True)

    confpath = "wsl-distribution.conf"

    fullpath = etcpath / confpath

    options = {
        "oobe": {
            "default_name": "RedHatEnterpriseLinux-10.0",
            "default_uid": 1000,
        },
        "shortcut": {
            "enabled": True,
            "icon": "/usr/share/pixmaps/fedora-logo.ico",
        }
    }

    stage_module.main(treepath, options)

    assert fullpath.exists()

    confdata = fullpath.read_text()

    assert confdata == """\
[oobe]
defaultUid = 1000
defaultName = RedHatEnterpriseLinux-10.0

[shortcut]
enabled = true
icon = /usr/share/pixmaps/fedora-logo.ico"""
