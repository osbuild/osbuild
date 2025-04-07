#!/usr/bin/python3

import os
import subprocess
import textwrap

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.systemd.unit.create"


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
            "filename": "foo.mount",
            "config": {
                "Unit": {},
                "Mount": {"What": "", "Where": ""},
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "foo.socket",
            "config": {
                "Socket": {"ListenStream": "/run/test/api.socket"},
            },
        },
        "",
    ),
    (
        {
            "filename": "foo.swap",
            "config": {
                "Swap": {"What": ""},
            },
        },
        "",
    ),
    (
        {
            "filename": "stdout-test.service",
            "config": {
                "Unit": {},
                "Service": {
                    "StandardOutput": "inherit",
                },
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "stdout-test.service",
            "config": {
                "Unit": {},
                "Service": {
                    "StandardOutput": "null",
                },
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "stdout-test.service",
            "config": {
                "Unit": {},
                "Service": {
                    "StandardOutput": "tty",
                },
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "stdout-test.service",
            "config": {
                "Unit": {},
                "Service": {
                    "StandardOutput": "journal",
                },
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "stdout-test.service",
            "config": {
                "Unit": {},
                "Service": {
                    "StandardOutput": "kmsg",
                },
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "stdout-test.service",
            "config": {
                "Unit": {},
                "Service": {
                    "StandardOutput": "journal+console",
                },
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "stdout-test.service",
            "config": {
                "Unit": {},
                "Service": {
                    "StandardOutput": "kmsg+console",
                },
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "stdout-test.service",
            "config": {
                "Unit": {},
                "Service": {
                    "StandardOutput": "file:/var/log/example.log",
                },
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "stdout-test.service",
            "config": {
                "Unit": {},
                "Service": {
                    "StandardOutput": "append:/var/log/app.log",
                },
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "stdout-test.service",
            "config": {
                "Unit": {},
                "Service": {
                    "StandardOutput": "append:/root/important.txt",
                },
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "stdout-test.service",
            "config": {
                "Unit": {},
                "Service": {
                    "StandardOutput": "truncate:/debug.log",
                },
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "stdout-test.service",
            "config": {
                "Unit": {},
                "Service": {
                    "StandardOutput": "socket",
                },
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "stdout-test.service",
            "config": {
                "Unit": {},
                "Service": {
                    "StandardOutput": "fd:stdout",
                },
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "stdout-test.service",
            "config": {
                "Unit": {},
                "Service": {
                    "StandardOutput": "fd:whatever",
                },
                "Install": {},
            },
        },
        "",
    ),

    # bad
    # # No filename
    ({"config": {"Unit": {}, "Service": {}, "Install": {}}}, "'filename' is a required property"),

    # # no config block
    ({"filename": "foo.service"}, "'config' is a required property"),

    # # no Unit section in .service
    ({"filename": "foo.service", "config": {"Service": {}, "Install": {}}},
     "{'Service': {}, 'Install': {}} is not valid under any of the given schemas"),

    # # no Service section in .service
    ({"filename": "foo.service", "config": {"Unit": {}, "Install": {}}},
     "{'Unit': {}, 'Install': {}} is not valid under any of the given schemas"),

    # # no Install section in .service
    ({"filename": "foo.service", "config": {"Unit": {}, "Service": {}}},
     "{'Unit': {}, 'Service': {}} is not valid under any of the given schemas"),

    # # .mount unit without Where
    ({"filename": "foo.mount", "config": {"Unit": {}, "Mount": {"What": ""}, "Install": {}}},
     "'Where' is a required property"),

    # # .mount unit without What
    ({"filename": "foo.mount", "config": {"Unit": {}, "Mount": {"Where": ""}, "Install": {}}},
     "'What' is a required property"),

    # # .service unit with Mount section
    ({"filename": "foo.service", "config": {"Unit": {}, "Service": {},
                                            "Mount": {"What": "", "Where": ""}, "Install": {}}},
     "{'Unit': {}, 'Service': {}, 'Mount': {'What': '', 'Where': ''}, "
     "'Install': {}} is not valid under any of the given schemas"),

    # # .swap unit with Service section
    ({"filename": "foo.swap", "config": {"Unit": {}, "Service": {}, "Swap": {"What": ""}, "Install": {}}},
     "{'Unit': {}, 'Service': {}, 'Swap': {'What': ''}, "
     "'Install': {}} is not valid under any of the given schemas"),

    # # bad StandardOutput values
    (
        {
            "filename": "stdout-test.service",
            "config": {
                "Unit": {},
                "Service": {
                    "StandardOutput": "syslog",
                },
                "Install": {},
            },
        },
        "'syslog' does not match",
    ),
    (
        {
            "filename": "stdout-test.service",
            "config": {
                "Unit": {},
                "Service": {
                    "StandardOutput": "file:",
                },
                "Install": {},
            },
        },
        "'file:' does not match",
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
            "filename": "foo.mount",
            "config": {
                "Unit": {},
                "Mount": {"What": "", "Where": ""},
                "Install": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "foo.socket",
            "config": {
                "Socket": {},
            },
        },
        "",
    ),
    (
        {
            "filename": "foo.swap",
            "config": {
                "Swap": {},
            },
        },
        "",
    ),
    # bad
    ({"filename": "something.service", "config": {"Unit": {}, "Mount": {}, "Install": {}}},
     "Error: something.service unit requires Service section"),
    ({"filename": "data-gifs-cats.mount", "config": {"Unit": {}, "Service": {}, "Install": {}}},
     "Error: data-gifs-cats.mount unit requires Mount section"),
    ({"filename": "data-gifs-cats.socket", "config": {"Unit": {}, "Service": {}, "Install": {}}},
     "Error: data-gifs-cats.socket unit requires Socket section"),
    ({"filename": "data-gifs-cats.swap", "config": {"Unit": {}, "Service": {}, "Install": {}}},
     "Error: data-gifs-cats.swap unit requires Swap section"),
])
def test_name_config_match(tmp_path, stage_module, test_data, expected_err):
    expected_unit_path = tmp_path / "usr/lib/systemd/system"
    expected_unit_path.mkdir(parents=True, exist_ok=True)
    try:
        stage_module.main(tmp_path, test_data)
    except ValueError as ve:
        assert expected_err == str(ve)


@pytest.mark.parametrize("unit_type,unit_path,expected_prefix", [
    ("system", "usr", "usr/lib/systemd/system"),
    ("system", "etc", "etc/systemd/system"),
    ("global", "usr", "usr/lib/systemd/user"),
    ("global", "etc", "etc/systemd/user"),
])
def test_systemd_unit_create(tmp_path, stage_module, unit_type, unit_path, expected_prefix):
    options = {
        "filename": "create-directory.service",
        "unit-type": unit_type,
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
            "Service": {
                "Type": "oneshot",
                "RemainAfterExit": True,
                "ExecStart": [
                    "/usr/bin/mkdir -p /etc/mydir",
                    "/usr/bin/touch /etc/myfile"
                ],
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
                "EnvironmentFile": [
                    "/etc/example.env",
                    "/etc/second.env",
                ],
                "StandardOutput": "append:/var/log/mkdir.log",
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

    # create units in the tree for systemd-analyze verify
    systemd_dir = "usr/lib/systemd/system/"
    # if a unit file is empty, it gets detected as "masked" and fails verification
    testutil.make_fake_tree(tmp_path, {
        systemd_dir + "basic.target": "[Unit]\n",
        systemd_dir + "sysinit.target": "[Unit]\n",
        systemd_dir + "paths.target": "[Unit]\n",
        systemd_dir + "sockets.target": "[Unit]\n",
        "usr/bin/mkdir": "fake-mkdir",
        "usr/bin/touch": "fake-touch",
    })
    for bin_name in ["mkdir", "touch"]:
        os.chmod(tmp_path / "usr/bin" / bin_name, mode=0o755)

    expected_unit_path = tmp_path / expected_prefix / "create-directory.service"
    expected_unit_path.parent.mkdir(parents=True, exist_ok=True)

    stage_module.main(tmp_path, options)
    assert os.path.exists(expected_unit_path)
    if unit_type == "system":
        # When verifying user units, systemd expects runtime directories and more generally a booted system. Setting
        # something up like that to verify it is more trouble than it's worth, especially since the system units are
        # identical.
        subprocess.run(["systemd-analyze", "verify",
                        "--man=no",  # disable manpage checks
                        f"--root={tmp_path}",  # verify commands and units in the root tree
                        expected_unit_path],
                       check=True)
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

    [Service]
    Type=oneshot
    RemainAfterExit=True
    ExecStart=/usr/bin/mkdir -p /etc/mydir
    ExecStart=/usr/bin/touch /etc/myfile
    Environment="DEBUG=1"
    Environment="TRACE=1"
    EnvironmentFile=/etc/example.env
    EnvironmentFile=/etc/second.env
    StandardOutput=append:/var/log/mkdir.log

    [Install]
    WantedBy=local-fs.target
    RequiredBy=multi-user.target

    """)


@pytest.mark.parametrize("unit_type,unit_path,expected_prefix", [
    ("system", "usr", "usr/lib/systemd/system"),
    ("system", "etc", "etc/systemd/system"),
    ("global", "usr", "usr/lib/systemd/user"),
    ("global", "etc", "etc/systemd/user"),
])
def test_systemd_unit_create_mount(tmp_path, stage_module, unit_type, unit_path, expected_prefix):
    options = {
        "filename": "data-test.mount",
        "unit-type": unit_type,
        "unit-path": unit_path,
        "config": {
            "Unit": {
                "DefaultDependencies": True,
                "ConditionPathExists": [
                    "/data"
                ],
                "ConditionPathIsDirectory": [
                    "/data"
                ],
                "Before": [
                    "local-fs.target",
                ],
            },
            "Mount": {
                "What": "/dev/sda2",
                "Where": "/data/test",
                "Type": "xfs",
                "Options": "rw,noatime"
            }
        }
    }

    # create units in the tree for systemd-analyze verify
    systemd_dir = "usr/lib/systemd/system/"
    # if a unit file is empty, it gets detected as "masked" and fails verification
    testutil.make_fake_tree(tmp_path, {
        systemd_dir + "basic.target": "[Unit]\n",
        systemd_dir + "sysinit.target": "[Unit]\n",
        systemd_dir + "paths.target": "[Unit]\n",
        systemd_dir + "sockets.target": "[Unit]\n",
        "usr/bin/mkdir": "fake-mkdir",
        "usr/bin/touch": "fake-touch",
    })
    for bin_name in ["mkdir", "touch"]:
        os.chmod(tmp_path / "usr/bin" / bin_name, mode=0o755)

    expected_unit_path = tmp_path / expected_prefix / "data-test.mount"
    expected_unit_path.parent.mkdir(parents=True, exist_ok=True)

    stage_module.main(tmp_path, options)
    assert os.path.exists(expected_unit_path)
    if unit_type == "system":
        # When verifying user units, systemd expects runtime directories and more generally a booted system. Setting
        # something up like that to verify it is more trouble than it's worth, especially since the system units are
        # identical.
        subprocess.run(["systemd-analyze", "verify",
                        "--man=no",  # disable manpage checks
                        f"--root={tmp_path}",  # verify commands and units in the root tree
                        expected_unit_path],
                       check=True)
    assert expected_unit_path.read_text(encoding="utf-8") == textwrap.dedent("""\
    [Unit]
    DefaultDependencies=True
    ConditionPathExists=/data
    ConditionPathIsDirectory=/data
    Before=local-fs.target

    [Mount]
    What=/dev/sda2
    Where=/data/test
    Type=xfs
    Options=rw,noatime

    """)
