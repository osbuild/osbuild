#!/usr/bin/python3

from unittest.mock import call, patch

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.bootupd"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({"deployment": "must-be-object"}, "'must-be-object' is not of type 'object'"),
    ({"deployment": {"osname": "some-os"}}, "{'osname': 'some-os'} is not valid under any of the given schemas"),
    ({"deployment": {"ref": "some-ref"}}, "{'ref': 'some-ref'} is not valid under any of the given schemas"),
    ({"deployment": {"osname": "some-os", "ref": "some-ref", "serial": "must-be-number"}},
     "'must-be-number' is not of type 'number'"),
    ({"deployment": {"default": False}}, "{'default': False} is not valid under any of the given schemas"),
    ({"deployment": {
        "osname": "some-os",
        "ref": "some-ref",
        "serial": 0,
        "default": True}
      }, "{'osname': 'some-os', 'ref': 'some-ref', 'serial': 0, 'default': True} is not valid under any of the given schemas"),
    ({"random": "property"}, "Additional properties are not allowed"),
    ({"bios": {}}, "'device' is a required property"),
    ({"bios": "must-be-object"}, "'must-be-object' is not of type 'object'"),
    # good
    ({}, ""),
    ({
        "deployment":
        {
            "osname": "some-os",
            "ref": "some-ref",
            "serial": 1,
        },
        "static-configs": True,
        "bios":
        {
            "device": "/dev/sda",
        },
    }, ""),
    ({
        "deployment":
        {
            "default": True,
        },
        "static-configs": True,
        "bios":
        {
            "device": "/dev/sda",
        },
    }, "")

])
def test_bootupd_schema_validation(stage_schema, test_data, expected_err):
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


@pytest.mark.parametrize("test_options,expected_bootupd_opts", [
    ({}, []),
    ({"bios": {"device": "/dev/sda"}}, ["--device=/mapped/dev/sda"]),
    ({"static-configs": True}, ["--with-static-configs"]),
])
@patch("subprocess.run")
def test_bootupd_defaults(mocked_run, stage_module, test_options, expected_bootupd_opts):
    args = {
        "paths": {
            "mounts": "/run/osbuild/mounts",
        },
        "devices": {
            "/dev/sda": {
                "path": "/mapped/dev/sda",
            },
        },
    }
    options = test_options
    with patch.object(stage_module, "bind_mounts") as mocked_bind_mounts:
        stage_module.main(args, options)

    assert len(mocked_bind_mounts.call_args_list) == 1
    assert mocked_run.call_args_list == [call(["chroot",
                                               "/run/osbuild/mounts",
                                               "/usr/bin/bootupctl",
                                               "backend",
                                               "install"] + expected_bootupd_opts + ["/run/osbuild/mounts"],
                                              check=True),
                                         ]


@patch("subprocess.run")
def test_bootupd_bind_mounts(mocked_run, stage_module):
    dst = "/run/osbuild/mounts/"
    with stage_module.bind_mounts(['/dev', '/proc', '/sys', '/run', '/var', '/tmp'], dst):
        pass
    assert mocked_run.call_args_list == [
        call(["mount", "--rbind", "/dev", "/run/osbuild/mounts/dev"], check=True),
        call(["mount", "--rbind", "/proc", "/run/osbuild/mounts/proc"], check=True),
        call(["mount", "--rbind", "/sys", "/run/osbuild/mounts/sys"], check=True),
        call(["mount", "--rbind", "/run", "/run/osbuild/mounts/run"], check=True),
        call(["mount", "--rbind", "/var", "/run/osbuild/mounts/var"], check=True),
        call(["mount", "--rbind", "/tmp", "/run/osbuild/mounts/tmp"], check=True),
        # and umount in reverse order
        call(["umount", "--recursive", "/run/osbuild/mounts/tmp"], check=False),
        call(["umount", "--recursive", "/run/osbuild/mounts/var"], check=False),
        call(["umount", "--recursive", "/run/osbuild/mounts/run"], check=False),
        call(["umount", "--recursive", "/run/osbuild/mounts/sys"], check=False),
        call(["umount", "--recursive", "/run/osbuild/mounts/proc"], check=False),
        call(["umount", "--recursive", "/run/osbuild/mounts/dev"], check=False),
    ]
