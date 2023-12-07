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
    ({"reboot": True}, "reboot"),
    ({"reboot": {"eject": False}}, "reboot"),
    ({"reboot": {"eject": True}}, "reboot --eject"),
    ({"reboot": {"kexec": False}}, "reboot"),
    ({"reboot": {"kexec": True}}, "reboot --kexec"),
    ({"reboot": {"eject": True, "kexec": True}}, "reboot --eject --kexec"),
    ({"display_mode": "text"}, "text"),
    ({"display_mode": "graphical"}, "graphical"),
    ({"display_mode": "cmdline"}, "cmdline"),
    # autopart
    ({"autopart": {}}, "autopart"),
    ({"autopart": {"type": "plain"}}, "autopart --type=plain"),
    ({"autopart": {"fstype": "ext4"}}, "autopart --fstype=ext4"),
    ({"autopart": {"nolvm": True}}, "autopart --nolvm"),
    ({"autopart": {"encrypted": True}}, "autopart --encrypted"),
    ({"autopart": {"passphrase": "secret"}}, "autopart --passphrase=secret"),
    ({"autopart": {"escrowcert": "http://escrow"}}, "autopart --escrowcert=http://escrow"),
    ({"autopart": {"backuppassphrase": True}}, "autopart --backuppassphrase"),
    ({"autopart": {"cipher": "aes-xts-plain2048"}}, "autopart --cipher=aes-xts-plain2048"),
    ({"autopart": {"luks-version": "42"}}, "autopart --luks-version=42"),
    ({"autopart": {"pbkdf": "scrypt"}}, "autopart --pbkdf=scrypt"),
    ({"autopart": {"pbkdf-memory": 64}}, "autopart --pbkdf-memory=64"),
    ({"autopart": {"pbkdf-time": 128}}, "autopart --pbkdf-time=128"),
    ({"autopart": {"pbkdf-iterations": 256}}, "autopart --pbkdf-iterations=256"),
    ({
        "lang": "en_US.UTF-8",
        "keyboard": "us",
        "timezone": "UTC",
        "zerombr": True,
        "clearpart": {
            "all": True,
            "drives": [
                "sd*|hd*|vda",
                "/dev/vdc"
            ]
        },
        "autopart": {
            "type": "lvm",
            "fstype": "zfs",
            "nolvm": True,
            "encrypted": True,
            "passphrase": "secret2",
            "escrowcert": "http://some-url",
            "backuppassphrase": True,
            "cipher": "twofish-cbc",
            "luks-version": "2",
            "pbkdf": "scrypt",
            "pbkdf-memory": 256,
            "pbkdf-time": 512,
            # pbkdf-iterations cannot be used together with time
        },
    },
        "lang en_US.UTF-8\nkeyboard us\ntimezone UTC\nzerombr\n" +
        "clearpart --all --drives=sd*|hd*|vda,/dev/vdc\n" +
        "autopart --type=lvm --fstype=zfs --nolvm --encrypted" +
        " --passphrase=secret2 --escrowcert=http://some-url" +
        " --backuppassphrase --cipher=twofish-cbc --luks-version=2" +
        " --pbkdf=scrypt --pbkdf-memory=256 --pbkdf-time=512"
    ),
    # network is always a list
    ({"network": [{"device": "foo", "activate": False}, {"device": "bar", "bootproto": "dhcp"}]},
     "network --device=foo --no-activate\nnetwork --device=bar --bootproto=dhcp"),
    ({"network": [{"device": "foo", "activate": True}]}, "network --device=foo --activate"),
    ({"network": [{"device": "foo", "activate": False}]}, "network --device=foo --no-activate"),
    ({"network": [{"device": "foo", "bootproto": "dhcp"}]}, "network --device=foo --bootproto=dhcp"),
    ({"network": [{"device": "foo", "onboot": "on"}]}, "network --device=foo --onboot=on"),
    ({"network": [{"device": "foo", "ip": "10.0.0.2"}]}, "network --device=foo --ip=10.0.0.2"),
    ({"network": [{"device": "foo", "ip": "auto"}]}, "network --device=foo --ip=auto"),
    ({"network": [{"device": "foo", "ipv6": "3ffe:ffff:0:1::1/128"}]},
     "network --device=foo --ipv6=3ffe:ffff:0:1::1/128"),
    ({"network": [{"device": "foo", "ipv6": "dhcp"}]}, "network --device=foo --ipv6=dhcp"),
    ({"network": [{"device": "foo", "gateway": "10.0.0.1"}]}, "network --device=foo --gateway=10.0.0.1"),
    ({"network": [{"device": "foo", "ipv6gateway": "FE80::1"}]}, "network --device=foo --ipv6gateway=FE80::1"),
    ({"network": [{"device": "foo", "nameservers": ["1.1.1.1"]}]}, "network --device=foo --nameserver=1.1.1.1"),
    ({"network": [{"device": "foo", "nameservers": ["1.1.1.1", "8.8.8.8"]}]},
     "network --device=foo --nameserver=1.1.1.1 --nameserver=8.8.8.8"),
    ({"network": [{"device": "foo", "netmask": "255.255.0.0"}]}, "network --device=foo --netmask=255.255.0.0"),
    ({"network": [{"device": "foo", "hostname": "meep"}]}, "network --device=foo --hostname=meep"),
    ({"network": [{"device": "foo", "essid": "wlan-123"}]}, "network --device=foo --essid=wlan-123"),
    ({"network": [{"device": "foo", "wpakey": "secret"}]}, "network --device=foo --wpakey=secret"),
    # device= can be written in multiple forms, see
    # https://pykickstart.readthedocs.io/en/latest/kickstart-docs.html#network
    ({"network": [{"device": "1234567890123456"}]}, "network --device=1234567890123456"),
    ({"network": [{"device": "em1"}]}, "network --device=em1"),
    ({"network": [{"device": "01:23:45:67:89:ab"}]}, "network --device=01:23:45:67:89:ab"),
    ({"network": [{"device": "link"}]}, "network --device=link"),
    ({"network": [{"device": "bootif"}]}, "network --device=bootif"),
    # hostname alone can be 63 chars (see hostname(7))
    ({"network": [{"device": "foo", "hostname": "123456789012345678901234567890123456789012345678901234567890123"}]},
     "network --device=foo --hostname=123456789012345678901234567890123456789012345678901234567890123"),
    # hostname can also be written as a QFDN
    ({"network": [{"device": "foo", "hostname": "foo.bar.com"}]},
     "network --device=foo --hostname=foo.bar.com"),
    # ostreecontainer
    (
        {
            "ostreecontainer": {
                "stateroot": "some-osname",
                "url": "http://some-ostree-url.com/foo",
                "transport": "registry",
                "remote": "some-remote",
                "signatureverification": False,
            },
        },
        "ostreecontainer --url=http://some-ostree-url.com/foo --stateroot=some-osname --transport=registry --remote=some-remote --no-signature-verification",
    ),
    (
        {
            "ostreecontainer": {
                "url": "http://some-ostree-url.com/foo",
            },
        },
        "ostreecontainer --url=http://some-ostree-url.com/foo",
    ),
]


def schema_validate_kickstart_stage(test_data):
    name = "org.osbuild.kickstart"
    version = "1"
    root = os.path.join(os.path.dirname(__file__), "../..")
    mod_info = osbuild.meta.ModuleInfo.load(root, "Stage", name)
    schema = osbuild.meta.Schema(mod_info.get_schema(version=version), name)
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
        ({"display_mode": "invalid-mode"}, "'invalid-mode' is not one of "),
        # autopart
        ({"autopart": {"type": "not-valid"}}, "'not-valid' is not one of ["),
        # Only one of --pbkdf-{time,iterations} can be specified at the same time
        ({"autopart": {"pbkdf-time": 1, "pbkdf-iterations": 2}}, " should not be valid under "),
        # network is always a list
        ({"network": {"device": "foo"}}, " is not of type 'array'"),
        ({"network": [{"device": "foo", "activate": "string"}]}, " is not of type 'boolean'"),
        ({"network": [{"device": "foo", "random": "option"}]}, "Additional properties are not allowed "),
        ({"network": [{"device": "foo", "bootproto": "invalid"}]}, " is not one of ["),
        ({"network": [{"device": "foo", "ip": "invalid"}]}, " does not match "),
        ({"network": [{"device": "foo", "ip": "256.1.1.1"}]}, " does not match "),
        ({"network": [{"device": "foo", "ip": "1.256.1.1"}]}, " does not match "),
        ({"network": [{"device": "foo", "ip": "1.1.256.1"}]}, " does not match "),
        ({"network": [{"device": "foo", "ip": "1.1.1.256"}]}, " does not match "),
        # kernel will accept this (and make it 127.0.0.1) but it's
        # technically not valid. if this becomes a problem we may need to
        # relax (or remove) the ipv4 validation regex. Also
        # 127.256 will be accepted and overflows into "127.0.1.0".
        ({"network": [{"device": "foo", "ip": "127.1"}]}, " does not match "),
        ({"network": [{"device": "foo", "gateway": "invalid"}]}, " does not match "),
        ({"network": [{"device": "foo", "nameservers": ["invalid"]}]}, " does not match "),
        # schema says at least 2 chars (this is arbitrary)
        ({"network": [{"device": "f"}]}, " does not match "),
        # device name can be max 16 chars (see IFNAMSIZ in the kernel source)
        # but otherwise are very free from, see
        # https://elixir.bootlin.com/linux/v6.6.1/source/net/core/dev.c#L1038
        ({"network": [{"device": "12345678901234567"}]}, " does not match "),
        # when specificed via MAC address it 17 chars (12 chars plus 5 ":")
        # and look like a mac address
        ({"network": [{"device": "00:01"}]}, " does not match "),
        ({"network": [{"device": "00:XX"}]}, " does not match "),
        ({"network": [{"device": "foo/bar"}]}, " does not match "),
        ({"network": [{"device": "foo?"}]}, " does not match "),
        # see hostname(7)
        ({"network": [{"device": "foo",
                       "hostname": "1234567890123456789012345678901234567890123456789012345678901234"}]}, " does not match "),
        ({"network": [{"device": "foo", "hostname": "x$"}]}, " does not match "),
        ({"network": [{"device": "foo", "hostname": "-invalid"}]}, " does not match "),
        ({"network": [{"device": "foo", "hostname": "foo..bar"}]}, " does not match "),
        # not more than 253 chars (63*3 + 62 + 3 dots = 254)
        ({"network": [{"device": "foo",
                       "hostname":
                       "123456789012345678901234567890123456789012345678901234567890123" +
                       ".123456789012345678901234567890123456789012345678901234567890123" +
                       ".123456789012345678901234567890123456789012345678901234567890123" +
                       ".12345678901234567890123456789012345678901234567890123456789012"
                       }]}, " does not match "),
        # ostreecontainer
        ({"ostreecontainer": {"url": "http://some-ostree-url.com/foo",
         "transport": "not-valid"}}, "'not-valid' is not one of ["),
        # not both ostreecontainer and ostree
        (
            {
                "ostreecontainer": {
                    "url": "http://some-ostree-url.com/foo",
                },
                "ostree": {
                    "osname": "some-osname",
                    "url": "http://some-ostree-url.com/foo",
                    "ref": "some-ref",
                    "remote": "some-remote",
                    "gpg": True,
                },
            },
            "is not valid under any of the given schemas",
        ),

    ],
)
def test_schema_validation_bad_apples(test_data, expected_err):
    res = schema_validate_kickstart_stage(test_data)

    assert res.valid is False
    assert len(res.errors) == 1
    err_msgs = [e.as_dict()["message"] for e in res.errors]
    assert expected_err in err_msgs[0]
