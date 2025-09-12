#!/usr/bin/python3

import os
import pathlib
import pytest
from unittest import mock

from osbuild import testutil

STAGE_NAME = "org.osbuild.systemd-sysusers"


@pytest.mark.parametrize("test_data,expected_err", [
    # good
    (
        {
        },
        "",
    ),
    (
        {
            "paths": [],
            "apply": True,
        },
        "",
    ),
    (
        {
            "paths": ["input://input/a-file"],
        },
        "",
    ),
    (
        {
            "paths": ["mount://mount/b-file"],
        },
        "",
    ),
    (
        {
            "paths": ["tree:///tree/c-file"],
        },
        "",
    ),
    (
        {
            "config": {
                "filename": "new.conf",
                "entries": [
                    {
                            "type": "u",
                            "name": "test-user",
                    }
                ]
            }
        },
        "",
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
                ]
            }
        },
        "",
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
                ]
            }
        },
        "",
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
                ]
            }
        },
        "",
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
                ]
            }
        },
        "",
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
                ]
            }
        },
        "",
    ),
    (
        {
            "paths": ["tree:///tree/c-file"],
            "config": {
                "filename": "new.conf",
                "entries": [
                    {
                            "type": "u",
                            "name": "very-long-user_with_number-1234",
                    }
                ]
            },
            "apply": False,
        },
        "",
    ),


    # bad
    # required field 'filename' of config is missing
    (
        {
            "config": {
                "entries": []
            },
        },
        "'filename' is a required property",
    ),
    # required field 'entries' of config is missing
    (
        {
            "config": {
                "filename": "new.conf"
            },
        },
        "'entries' is a required property",
    ),
    # required field 'filename' is invalid
    (
        {
            "config": {
                "filename": "new.cof",
                "entries": []
            },
        },
        "'new.cof' does not match '\\\\.conf$'",
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
                ]
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
                ]
            },
        },
        "'type' is a required property",
    ),
    # invalid field 'type' of entries
    (
        {
            "config": {
                "filename": "new.conf",
                "entries": [
                    {
                        "type": "x",
                        "name": "test-user"
                    }
                ]
            },
        },
        "'x' is not one of ['u', 'u!', 'g', 'm', 'r']",
    ),
    # invalid field 'name' of entries - too long
    (
        {
            "config": {
                "filename": "new.conf",
                "entries": [
                    {
                        "type": "u",
                        "name": "too-long-user_with_number-1234-and-more"
                    }
                ]
            },
        },
        "too-long-user_with_number-1234-and-more' does not match '^[a-zA-Z_][a-zA-Z0-9_-]{0,30}$",
    ),
    # invalid path
    (
        {
            "paths": ["/input/a-file"],
        },
        "'/input/a-file' is not valid under any of the given schemas",
    ),
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


def test_systemd_sysusers_paths(tmp_path, stage_module):
    options = {
        "paths": [
            "tree:///var/new-a.conf",
            "tree:///var/new-b.conf",
        ],
        "apply": False,
    }

    sysusers_d_dir = "etc/sysusers.d"
    new_a_conf_content = """
u flatpak - "Flatpak system helper" -
"""
    new_b_conf_content = """
#Type  Name  ID  GECOS                 Home directory  Shell
u      dbus  81  "System Message Bus"  -               -
"""
    testutil.make_fake_tree(tmp_path, {
        "var/new-a.conf": new_a_conf_content,
        "var/new-b.conf": new_b_conf_content,
    })
    os.makedirs(tmp_path / sysusers_d_dir)

    stage_module.main({
        "tree": tmp_path,
        "options": options
    })

    expected_conf_path_a = tmp_path / sysusers_d_dir / "new-a.conf"
    expected_conf_path_b = tmp_path / sysusers_d_dir / "new-b.conf"

    assert os.path.exists(expected_conf_path_a)
    assert os.path.exists(expected_conf_path_b)

    assert expected_conf_path_a.read_text(encoding="utf-8") == new_a_conf_content
    assert expected_conf_path_b.read_text(encoding="utf-8") == new_b_conf_content


@pytest.mark.parametrize("test_config,expected_content,expected_error", [
    # good
    # config is optional
    (
        None, "", "",
    ),
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
        "u sysuser-a -\n",
        "",
    ),
    (
        {
            "filename": "custom.conf",
            "entries": [
                {
                    "type": "u",
                    "name": "sysuser-a",
                    "id": "-"
                }
            ],
        },
        "u sysuser-a -\n",
        "",
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
                    "shell": "/bin/bash"
                }
            ],
        },
        "u sysuser-a 100 \"Test user for the system\" /home/sysuser /bin/bash\n",
        "",
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
        "u sysuser-a 100:200\n",
        "",
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
                    "shell": "/bin/bash"
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
                }
            ],
        },
        """u sysuser-a 100 \"Test user for the system\" /home/sysuser /bin/bash
g sysuser-a-group 101
m sysuser-a sysuser-a-group
r - 200-500
""",
        "",
    ),

    # bad
    # checking for missing required fields
    (
        {}, "", "'filename' is required",
    ),
    (
        {
            "filename": "custom.conf",
        },
        "",
        "'entries' is required",
    ),
    (
        {
            "entries": {},
        },
        "",
        "'filename' is required",
    ),
    (
        {
            "filename": "custom.conf",
            "entries": [{}],
        },
        "",
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
        "",
        "Error: sysuser entry 'Name=' is invalid: name needs to match regex '^-$|[a-zA-Z_][a-zA-Z0-9_-]{0,30}$'",
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
        "",
        "Error: sysuser entry 'Name=sysuser-a-with-a-very-very-long-id-123456' is invalid: name needs to match regex '^-$|[a-zA-Z_][a-zA-Z0-9_-]{0,30}$'",
    ),
    # checking id validation
    (
        {
            "filename": "custom.conf",
            "entries": [
                {
                    "type": "u",
                    "name": "sysuser-a",
                    "id": "blubb"
                },
            ],
        },
        "",
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
        "",
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
        "",
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
        "",
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
        "",
        "Error: sysuser entry 'ID=101' is invalid: id should be group name for m entry",
    ),

])
def test_systemd_sysusers_config(tmp_path, stage_module, test_config, expected_content, expected_error):
    options = {
        "config": test_config,
        "apply": False,
    }

    sysusers_d_dir = "etc/sysusers.d"
    os.makedirs(tmp_path / sysusers_d_dir)

    if expected_error != "":
        raised_error = ""
        try:
            stage_module.main({
                "tree": tmp_path,
                "options": options
            })
        except Exception as ex:
            raised_error = f"{ex}"
        assert raised_error == expected_error
        return
    else:
        stage_module.main({
            "tree": tmp_path,
            "options": options
        })

    if test_config and "filename" in test_config:
        expected_conf_path = tmp_path / sysusers_d_dir / test_config["filename"]
        if "entries" in test_config and test_config["entries"]:
            assert os.path.exists(expected_conf_path)
            assert expected_conf_path.read_text(encoding="utf-8") == expected_content
        else:
            assert not os.path.exists(expected_conf_path)


@mock.patch("subprocess.run")
@pytest.mark.parametrize("test_options", [
    (
        {}
    ),
    (
        {
            "paths": [],
            "config": None,
        }
    ),
    (
        {
            "paths": ["tree:///var/a.conf"],
            "config": {
                "filename": "new.conf",
                "entries": [
                    {
                        "type": "u",
                        "name": "sysuser",
                    }
                ],
            }
        }
    ),
])
def test_systemd_sysusers_config(mock_run, tmp_path, stage_module, test_options):
    os.makedirs(tmp_path / "etc/sysusers.d")

    stage_module.main({
        "tree": tmp_path,
        "options": test_options
    })

    expected = [
        "systemd-sysusers",
        "--root",
        pathlib.Path(tmp_path),
    ]
    mock_run.assert_called_with(expected, check=True)
