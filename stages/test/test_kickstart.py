#!/usr/bin/python3

import os.path

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
])
def test_kickstart(tmp_path, test_input, expected):
    ks_stage_path = os.path.join(os.path.dirname(__file__), "../org.osbuild.kickstart")
    ks_stage = import_module_from_path("ks_stage", ks_stage_path)

    ks_path = "kickstart/kfs.cfg"
    options = {"path": ks_path}
    options.update(test_input)

    ks_stage.main(tmp_path, options)

    with open(os.path.join(tmp_path, ks_path), encoding="utf-8") as fp:
        ks_content = fp.read()
    assert ks_content == expected + "\n"
