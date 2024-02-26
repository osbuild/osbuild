#!/usr/bin/python3

import textwrap

import pytest

STAGE_NAME = "org.osbuild.coreos.platform"


def make_fake_platforms_json(json_file_path):
    json_file_path.write_text(textwrap.dedent("""\
    {
      "only-grub": {
        "grub_commands": [
          "serial --speed=115200"
        ]
      },
      "azure": {
        "kernel_arguments": [
          "console=tty0",
          "console=ttyS0,115200n8"
        ]
      },
      "vmware": {
        "grub_commands": [
          "serial --speed=115200",
          "terminal_input serial console",
          "terminal_output serial console"
        ],
        "kernel_arguments": [
          "console=ttyS0,115200n8",
          "console=tty0"
        ]
      }
    }"""), encoding="utf8")
    return json_file_path


@pytest.mark.parametrize("platform,expected_grub,expected_kernel", [
    # no key is no error
    ("missing", [], []),
    # one of each
    ("only-grub", ["serial --speed=115200"], []),
    # examples from:
    # "podman run --rm quay.io/fedora/fedora-coreos:stable cat /usr/share/coreos-assembler/platforms.json"
    # thanks dusty!
    ("azure", [], ['console=tty0', 'console=ttyS0,115200n8']),
    ("vmware", ["serial --speed=115200", "terminal_input serial console",
                "terminal_output serial console"], ["console=ttyS0,115200n8", "console=tty0"]),
])
def test_process_platforms_json(tmp_path, stage_module, platform, expected_grub, expected_kernel):
    fake_platforms_path = make_fake_platforms_json(tmp_path / "platforms.json")
    grub_cmds, kernel_args = stage_module.process_platforms_json(fake_platforms_path, platform)
    assert grub_cmds == expected_grub
    assert kernel_args == expected_kernel
