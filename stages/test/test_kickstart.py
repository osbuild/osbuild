#!/usr/bin/python3

import os.path
import subprocess

import pytest

from osbuild.testutil.imports import import_module_from_path


@pytest.mark.parametrize("test_input,expected", [
    ({"lang": "en_US.UTF-8"}, "lang en_US.UTF-8"),
    ({"keyboard": "us"}, "keyboard us"),
    ({"timezone": "UTC"}, "timezone UTC"),
    ({"lang": "en_US.UTF-8",
      "keyboard": "us",
      "timezone": "UTC",
      },
     "lang en_US.UTF-8\nkeyboard us\ntimezone UTC"),
    ({"ostree":
      {
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
     "ostreesetup --osname=some-osname --url=http://some-ostree-url.com/foo --ref=some-ref --remote=some-remote\n" +
     "liveimg --url some-liveimg-url\ngroup --name somegrp --gid 2337\n" +
     "user --name someusr --password $1$notreally --iscrypted --shell /bin/ksh --uid 1337 --gid 1337 --groups grp1,grp2 --homedir /other/home/someusr\n" +
     'sshkey --username someusr "ssh-rsa not-really-a-real-key"'
     ),
    ({"zerombr": "true"}, "zerombr"),
    ({"clearpart": {}}, "clearpart"),
    ({"clearpart": {"all": True}}, "clearpart --all"),
    ({"clearpart": {"drives": ["hda", "hdb"]}}, "clearpart --drives=hda,hdb",),
    ({"clearpart": {"drives": ["hda"]}}, "clearpart --drives=hda"),
    ({"clearpart": {"list": ["sda2", "sda3"]}}, "clearpart --list=sda2,sda3"),
    ({"clearpart": {"list": ["sda2"]}}, "clearpart --list=sda2"),
    ({"clearpart": {"disklabel": "some-label"}},
     "clearpart --disklabel=some-label",
     ),
    ({"clearpart": {"linux": True}}, "clearpart --linux"),
    ({"clearpart": {
        "all": True,
        "drives": ["hda", "hdb"],
        "list": ["sda2", "sda3"],
        "disklabel": "some-label",
        "linux": True,
    },
    },
        "clearpart --all --drives=hda,hdb --list=sda2,sda3 --disklabel=some-label --linux"),
    ({"lang": "en_US.UTF-8",
              "keyboard": "us",
              "timezone": "UTC",
              "zerombr": True,
              "clearpart": {
                  "all": True,
                  "drives": [
                      "sd*|hd*|vda",
                      "/dev/vdc"
                  ]
              }
      },
        "lang en_US.UTF-8\nkeyboard us\ntimezone UTC\nzerombr\nclearpart --all --drives=sd*|hd*|vda,/dev/vdc",
     ),
])
def test_kickstart(tmp_path, test_input, expected):
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

    # double check with pykickstart if the file looks valid
    subprocess.check_call(["ksvalidator", ks_path])
