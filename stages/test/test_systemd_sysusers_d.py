#!/usr/bin/python3

import os

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.systemd-sysusers.d"


@pytest.mark.parametrize(
    "test_data",
    [
        (
            {
                "config": {
                    "filename": "new.conf",
                    "entries": [
                        {
                            "type": "u",
                            "name": "test-user",
                        }
                    ],
                }
            },
        ),
        (
            {
                "config": {
                    "filename": "new.conf",
                    "entries": [
                        {
                            "type": "u!",
                            "name": "test-user",
                        }
                    ],
                }
            },
        ),
        (
            {
                "config": {
                    "filename": "new.conf",
                    "entries": [
                        {
                            "type": "g",
                            "name": "test-user",
                        }
                    ],
                }
            },
        ),
        (
            {
                "config": {
                    "filename": "new.conf",
                    "entries": [
                        {
                            "type": "m",
                            "name": "test-user",
                        }
                    ],
                }
            },
        ),
        (
            {
                "config": {
                    "filename": "new.conf",
                    "entries": [
                        {
                            "type": "r",
                            "name": "test-user",
                        }
                    ],
                }
            },
        ),
        (
            {
                "config": {
                    "filename": "new.conf",
                    "entries": [
                        {
                            "type": "u",
                            "name": "very-long-user_with_number-1234",
                        }
                    ],
                }
            },
        ),
        (
            {
                "config": {
                    "filename": "new.conf",
                    "entries": [
                        {
                            "type": "u",
                            "name": "very-long-user_with_number-1234",
                        }
                    ],
                },
            },
        ),
        # for type r the name needs to be a single dash symbol
        (
            {
                "config": {
                    "filename": "new.conf",
                    "entries": [{"type": "r", "name": "-"}],
                },
            },
        ),
    ],
)
@pytest.mark.parametrize("stage_schema", ["1"], indirect=True)
def test_schema_validation_good(stage_schema, test_data):
    test_input = {
        "name": STAGE_NAME,
        "options": test_data,
    }
    res = stage_schema.validate(test_input)
    assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"


@pytest.mark.parametrize(
    "test_data,expected_err",
    [
        # required field 'filename' of config is missing
        (
            {
                "config": {"entries": []},
            },
            "'filename' is a required property",
        ),
        # required field 'entries' of config is missing
        (
            {
                "config": {"filename": "new.conf"},
            },
            "'entries' is a required property",
        ),
        # required field 'filename' is invalid
        (
            {
                "config": {"filename": "new.cof", "entries": []},
            },
            "'new.cof' does not match '\\\\.conf$'",
        ),
        # field 'path-prefix' is invalid
        (
            {
                "config": {"path-prefix": "run", "filename": "new.conf", "entries": []},
            },
            "'run' is not one of ['usr', 'etc']",
        ),
        # required field 'type' of entries is missing
        (
            {
                "config": {
                    "filename": "new.conf",
                    "entries": [
                        {
                            "type": "u",
                        }
                    ],
                },
            },
            "'name' is a required property",
        ),
        # required field 'type' of entries is missing
        (
            {
                "config": {
                    "filename": "new.conf",
                    "entries": [
                        {
                            "name": "test-user",
                        }
                    ],
                },
            },
            "'type' is a required property",
        ),
        # invalid field 'type' of entries
        (
            {
                "config": {"filename": "new.conf", "entries": [{"type": "x", "name": "test-user"}]},
            },
            "'x' is not one of ['u', 'u!', 'g', 'm', 'r']",
        ),
        # invalid field 'name' of entries - too long
        (
            {
                "config": {
                    "filename": "new.conf",
                    "entries": [{"type": "u", "name": "too-long-user_with_number-1234-and-more"}],
                },
            },
            "'too-long-user_with_number-1234-and-more' does not match '^([a-z]+(?:[-_][a-zA-Z0-9_-]{0,30})?|-)$",
        ),
        # invalid field 'name' of entries - starts with dash symbol
        (
            {
                "config": {
                    "filename": "new.conf",
                    "entries": [{"type": "u", "name": "-also-invalid"}],
                },
            },
            "'-also-invalid' does not match '^([a-z]+(?:[-_][a-zA-Z0-9_-]{0,30})?|-)$",
        ),
    ],
)
@pytest.mark.parametrize("stage_schema", ["1"], indirect=True)
def test_schema_validation_bad(stage_schema, test_data, expected_err):
    test_input = {
        "name": STAGE_NAME,
        "options": test_data,
    }
    res = stage_schema.validate(test_input)
    assert res.valid is False
    testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


@pytest.mark.parametrize(
    "test_config,expected_content",
    [
        (
            {
                "filename": "custom.conf",
                "entries": [
                    {
                        "type": "u",
                        "name": "sysuser-a",
                    }
                ],
            },
            "u sysuser-a - - - -\n",
        ),
        (
            {
                "path-prefix": "etc",
                "filename": "custom.conf",
                "entries": [
                    {
                        "type": "u",
                        "name": "sysuser-a",
                    }
                ],
            },
            "u sysuser-a - - - -\n",
        ),
        (
            {
                "filename": "custom.conf",
                "entries": [{"type": "u", "name": "sysuser-a", "id": "-"}],
            },
            "u sysuser-a - - - -\n",
        ),
        (
            {
                "filename": "custom.conf",
                "entries": [
                    {
                        "type": "u",
                        "name": "sysuser-a",
                        "id": "100",
                        "gecos": "Test user for the system",
                        "home": "/home/sysuser",
                        "shell": "/bin/bash",
                    }
                ],
            },
            "u sysuser-a 100 \"Test user for the system\" /home/sysuser /bin/bash\n",
        ),
        (
            {
                "filename": "custom.conf",
                "entries": [
                    {
                        "type": "u",
                        "name": "sysuser-a",
                        "id": "100:200",
                    }
                ],
            },
            "u sysuser-a 100:200 - - -\n",
        ),
        (
            {
                "filename": "custom.conf",
                "entries": [
                    {
                        "type": "u",
                        "name": "sysuser-a",
                        "id": "100",
                        "gecos": "Test user for the system",
                        "home": "/home/sysuser",
                        "shell": "/bin/bash",
                    },
                    {
                        "type": "g",
                        "name": "sysuser-a-group",
                        "id": "101",
                    },
                    {
                        "type": "m",
                        "name": "sysuser-a",
                        "id": "sysuser-a-group",
                    },
                    {
                        "type": "r",
                        "name": "-",
                        "id": "200-500",
                    },
                ],
            },
            """u sysuser-a 100 \"Test user for the system\" /home/sysuser /bin/bash
g sysuser-a-group 101 - - -
m sysuser-a sysuser-a-group - - -
r - 200-500 - - -
""",
        ),
        (
            {
                "filename": "custom.conf",
                "entries": [
                    {
                        "type": "u",
                        "name": "sysuser-a",
                        "home": "/home/sysuser",
                        "shell": "/bin/bash",
                    },
                ],
            },
            """u sysuser-a - - /home/sysuser /bin/bash
""",
        ),
        (
            {
                "filename": "custom.conf",
                "entries": [
                    {
                        "type": "u",
                        "name": "sysuser-a",
                        "shell": "/bin/bash",
                    },
                ],
            },
            """u sysuser-a - - - /bin/bash
""",
        ),
    ]
)
def test_systemd_sysusers_d_config(tmp_path, stage_module, test_config, expected_content):
    options = {
        "config": test_config,
    }

    sysusers_d_dir = "usr/lib/sysusers.d"
    if "path-prefix" in test_config and test_config.get("path-prefix") == "etc":
        sysusers_d_dir = "etc/sysusers.d"
    os.makedirs(tmp_path / sysusers_d_dir)

    stage_module.main({"tree": tmp_path, "options": options})

    if test_config and "filename" in test_config:
        expected_conf_path = tmp_path / sysusers_d_dir / test_config["filename"]
        if "entries" in test_config and test_config["entries"]:
            assert os.path.exists(expected_conf_path)
            assert expected_conf_path.read_text(encoding="utf-8") == expected_content
        else:
            assert not os.path.exists(expected_conf_path)


@pytest.mark.parametrize(
    "test_config,expected_error",
    [
        # config is required
        (
            None,
            "'config' is required",
        ),
        # checking for missing required fields
        (
            {},
            "'filename' is required",
        ),
        (
            {
                "filename": "custom.conf",
            },
            "'entries' is required",
        ),
        (
            {
                "entries": {},
            },
            "'filename' is required",
        ),
        (
            {
                "filename": "custom.conf",
                "entries": [{}],
            },
            "Error: sysuser entry 'Type=' is invalid: type needs to be one of: ['u', 'u!', 'g', 'm', 'r']",
        ),
        (
            {
                "filename": "custom.conf",
                "entries": [
                    {
                        "type": "u",
                    }
                ],
            },
            "Error: sysuser entry 'Name=' is invalid: name needs to match regex '^([a-z]+(?:[-_][a-zA-Z0-9_-]{0,30})?|-)$'",
        ),
        # checking name validation
        (
            {
                "filename": "custom.conf",
                "entries": [
                    {
                        "type": "u",
                        "name": "sysuser-a-with-a-very-very-long-id-123456",
                    },
                ],
            },
            "Error: sysuser entry 'Name=sysuser-a-with-a-very-very-long-id-123456' is invalid: name needs to match regex '^([a-z]+(?:[-_][a-zA-Z0-9_-]{0,30})?|-)$'",
        ),
        # checking id validation
        (
            {
                "filename": "custom.conf",
                "entries": [
                    {"type": "u", "name": "sysuser-a", "id": "blubb"},
                ],
            },
            "invalid literal for int() with base 10: 'blubb'",
        ),
        (
            {
                "filename": "custom.conf",
                "entries": [
                    {
                        "type": "u",
                        "name": "sysuser-a",
                        "id": "100-200",
                    }
                ],
            },
            "invalid literal for int() with base 10: '100-200'",
        ),
        (
            {
                "filename": "custom.conf",
                "entries": [
                    {
                        "type": "r",
                        "name": "-",
                        "id": "200:500",
                    }
                ],
            },
            "invalid literal for int() with base 10: '200:500'",
        ),
        (
            {
                "filename": "custom.conf",
                "entries": [
                    {
                        "type": "r",
                        "name": "a-name",
                        "id": "200-500",
                    }
                ],
            },
            "Error: sysuser entry 'Name=a-name' is invalid: name needs to be '-' for type 'r'",
        ),
        (
            {
                "filename": "custom.conf",
                "entries": [
                    {
                        "type": "m",
                        "name": "a-user",
                        "id": "101",
                    }
                ],
            },
            "Error: sysuser entry 'ID=101' is invalid: id should be group name for m entry",
        ),
    ],
)
def test_systemd_sysusers_d_config_bad(tmp_path, stage_module, test_config, expected_error):
    options = {
        "config": test_config,
    }

    sysusers_d_dir = "etc/sysusers.d"
    os.makedirs(tmp_path / sysusers_d_dir)

    with pytest.raises(ValueError) as ex:
        stage_module.main({"tree": tmp_path, "options": options})
    assert expected_error in str(ex.value)
