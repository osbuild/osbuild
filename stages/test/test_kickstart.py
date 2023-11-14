#!/usr/bin/python3

import os.path
import subprocess

import pytest

import osbuild.meta
from osbuild.testutil import has_executable
from osbuild.testutil.imports import import_module_from_path

TEST_INPUT = [
    ({"lang": "en_US.UTF-8"}, "lang en_US.UTF-8"),
    ({"keyboard": "us"}, "keyboard us"),
    ({"timezone": "UTC"}, "timezone UTC"),
    (
        {
            "lang": "en_US.UTF-8",
            "keyboard": "us",
            "timezone": "UTC",
        },
        "lang en_US.UTF-8\nkeyboard us\ntimezone UTC",
    ),
    (
        {
            "ostree": {
                "osname": "some-osname",
                "url": "http://some-ostree-url.com/foo",
                "ref": "some-ref",
                "remote": "some-remote",
                "gpg": True,
            },
            "liveimg": {
                "url": "some-liveimg-url",
            },
            "groups": {
                "somegrp": {
                    "gid": 2337,
                },
            },
            "users": {
                "someusr": {
                    "uid": 1337,
                    "gid": 1337,
                    "groups": [
                        "grp1",
                        "grp2",
                    ],
                    "home": "/other/home/someusr",
                    "shell": "/bin/ksh",
                    "password": "$1$notreally",
                    "key": "ssh-rsa not-really-a-real-key",
                },
            },
        },
        "ostreesetup --osname=some-osname --url=http://some-ostree-url.com/foo --ref=some-ref --remote=some-remote\n"
        + "liveimg --url some-liveimg-url\ngroup --name somegrp --gid 2337\n"
        + "user --name someusr --password $1$notreally --iscrypted --shell /bin/ksh --uid 1337 --gid 1337 --groups grp1,grp2 --homedir /other/home/someusr\n"
        + 'sshkey --username someusr "ssh-rsa not-really-a-real-key"',
    ),
    ({"zerombr": True}, "zerombr"),
    ({"clearpart": {"all": True}}, "clearpart --all"),
    (
        {"clearpart": {"drives": ["sd*|hd*|vda", "/dev/vdc"]}},
        "clearpart --drives=sd*|hd*|vda,/dev/vdc",
    ),
    ({"clearpart": {"drives": ["hda"]}}, "clearpart --drives=hda"),
    (
        {"clearpart": {"drives": ["disk/by-id/scsi-58095BEC5510947BE8C0360F604351918"]}},
        "clearpart --drives=disk/by-id/scsi-58095BEC5510947BE8C0360F604351918"
    ),
    ({"clearpart": {"list": ["sda2", "sda3"]}}, "clearpart --list=sda2,sda3"),
    ({"clearpart": {"list": ["sda2"]}}, "clearpart --list=sda2"),
    (
        {"clearpart": {"disklabel": "some-label"}},
        "clearpart --disklabel=some-label",
    ),
    ({"clearpart": {"linux": True}}, "clearpart --linux"),
    (
        {
            "clearpart": {
                "all": True,
                "drives": ["hda", "hdb"],
                "list": ["sda2", "sda3"],
                "disklabel": "some-label",
                "linux": True,
            },
        },
        "clearpart --all --drives=hda,hdb --list=sda2,sda3 --disklabel=some-label --linux",
    ),
    (
        {
            "lang": "en_US.UTF-8",
            "keyboard": "us",
            "timezone": "UTC",
            "zerombr": True,
            "clearpart": {"all": True, "drives": ["sd*|hd*|vda", "/dev/vdc"]},
        },
        "lang en_US.UTF-8\nkeyboard us\ntimezone UTC\nzerombr\nclearpart --all --drives=sd*|hd*|vda,/dev/vdc",
    ),
    # no reboot for an empty dict
    ({"reboot": True}, "reboot"),
    ({"reboot": {"eject": False}}, "reboot"),
    ({"reboot": {"eject": True}}, "reboot --eject"),
    ({"reboot": {"kexec": False}}, "reboot"),
    ({"reboot": {"kexec": True}}, "reboot --kexec"),
    ({"reboot": {"eject": True, "kexec": True}}, "reboot --eject --kexec"),
]


def schema_validate_kickstart_stage(test_data):
    name = "org.osbuild.kickstart"
    root = os.path.join(os.path.dirname(__file__), "../..")
    mod_info = osbuild.meta.ModuleInfo.load(root, "Stage", name)
    schema = osbuild.meta.Schema(mod_info.get_schema(), name)
    test_input = {
        "name": "org.osbuild.kickstart",
        "options": {
            "path": "some-path",
        }
    }
    test_input["options"].update(test_data)
    return schema.validate(test_input)


@pytest.mark.parametrize("test_input,expected", TEST_INPUT)
def test_kickstart_test_cases_valid(test_input, expected):  # pylint: disable=unused-argument
    """ ensure all test inputs are valid """
    res = schema_validate_kickstart_stage(test_input)
    assert res.valid is True, f"input: {test_input}\nerr: {[e.as_dict() for e in res.errors]}"


@pytest.mark.parametrize("test_input,expected", TEST_INPUT)
def test_kickstart_write(tmp_path, test_input, expected):
    ks_stage_path = os.path.join(os.path.dirname(__file__), "../org.osbuild.kickstart")
    ks_stage = import_module_from_path("ks_stage", ks_stage_path)

    ks_path = "kickstart/kfs.cfg"
    options = {"path": ks_path}
    options.update(test_input)

    ks_stage.main(tmp_path, options)

    ks_path = os.path.join(tmp_path, ks_path)
    with open(ks_path, encoding="utf-8") as fp:
        ks_content = fp.read()
    assert ks_content == expected + "\n"


@pytest.mark.skipif(not has_executable("ksvalidator"), reason="`ksvalidator` is required")
@pytest.mark.parametrize("test_input,expected", TEST_INPUT)
def test_kickstart_valid(tmp_path, test_input, expected):  # pylint: disable=unused-argument
    ks_stage_path = os.path.join(os.path.dirname(__file__), "../org.osbuild.kickstart")
    ks_stage = import_module_from_path("ks_stage", ks_stage_path)

    ks_path = "kickstart/kfs.cfg"
    options = {"path": ks_path}
    options.update(test_input)

    ks_stage.main(tmp_path, options)

    ks_path = os.path.join(tmp_path, ks_path)

    # check with pykickstart if the file looks valid
    subprocess.check_call(["ksvalidator", ks_path])


@pytest.mark.parametrize(
    "test_data,expected_err",
    [
        # BAD pattern, ensure some obvious ways to write arbitrary
        # kickstart files will not work
        ({"clearpart": {}}, "{} is not valid "),
        ({"clearpart": {"disklabel": r"\n%pre\necho p0wnd"}}, r"p0wnd' does not match"),
        ({"clearpart": {"drives": [" --spaces-dashes-not-allowed"]}}, "' --spaces-dashes-not-allowed' does not match"),
        ({"clearpart": {"drives": ["\n%pre not allowed"]}}, "not allowed' does not match"),
        ({"clearpart": {"drives": ["no,comma"]}}, "no,comma' does not match"),
        ({"clearpart": {"list": ["\n%pre not allowed"]}}, "not allowed' does not match"),
        ({"clearpart": {"list": ["no,comma"]}}, "no,comma' does not match"),
        ({"clearpart": {"disklabel": "\n%pre not allowed"}}, "not allowed' does not match"),
        ({"clearpart": {"random": "option"}}, "is not valid "),
        # schema ensures reboot has at least one option set
        ({"reboot": {}}, "{} is not valid under any of the given schemas"),
        ({"reboot": "random-string"}, "'random-string' is not valid "),
        ({"reboot": {"random": "option"}}, "{'random': 'option'} is not valid "),
    ],
)
def test_schema_validation_bad_apples(test_data, expected_err):
    res = schema_validate_kickstart_stage(test_data)

    assert res.valid is False
    assert len(res.errors) == 1
    err_msgs = [e.as_dict()["message"] for e in res.errors]
    assert expected_err in err_msgs[0]
