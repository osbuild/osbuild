import os
import subprocess
from unittest.mock import patch

import pytest

from osbuild.testutil import make_fake_tree
from osbuild.testutil.imports import import_module_from_path

osbuild_image_info = import_module_from_path("osbuild_image_info", "tools/osbuild-image-info")


@pytest.mark.parametrize("fake_tree,entries", (
    # no entries
    ({}, []),
    # one entry
    (
        {
            "/boot/loader/entries/0649288e52434223afde4c36460a375e-6.11.9-100.fc39.x86_64.conf": """title Fedora Linux (6.11.9-100.fc39.x86_64) 39 (Thirty Nine)
version 6.11.9-100.fc39.x86_64
linux /boot/vmlinuz-6.11.9-100.fc39.x86_64
initrd /boot/initramfs-6.11.9-100.fc39.x86_64.img
options root=UUID=a7e970a5-14fb-4a8a-ab09-603d1ac3fee9 ro crashkernel=auto net.ifnames=0 rhgb console=tty0 console=ttyS0,115200n8
grub_users $grub_users
grub_arg --unrestricted
grub_class fedora""",
        },
        [
            {
                "title": "Fedora Linux (6.11.9-100.fc39.x86_64) 39 (Thirty Nine)",
                "version": "6.11.9-100.fc39.x86_64",
                "linux": "/boot/vmlinuz-6.11.9-100.fc39.x86_64",
                "initrd": "/boot/initramfs-6.11.9-100.fc39.x86_64.img",
                "options": "root=UUID=a7e970a5-14fb-4a8a-ab09-603d1ac3fee9 ro crashkernel=auto net.ifnames=0 rhgb console=tty0 console=ttyS0,115200n8",
                "grub_users": "$grub_users",
                "grub_arg": "--unrestricted",
                "grub_class": "fedora",
            },
        ]
    ),
    # two entries
    (
        {
            "/boot/loader/entries/0649288e52434223afde4c36460a375e-6.11.9-100.fc39.x86_64.conf": """title Fedora Linux (6.11.9-100.fc39.x86_64) 39 (Thirty Nine)
version 6.11.9-100.fc39.x86_64
linux /boot/vmlinuz-6.11.9-100.fc39.x86_64
initrd /boot/initramfs-6.11.9-100.fc39.x86_64.img
options root=UUID=a7e970a5-14fb-4a8a-ab09-603d1ac3fee9 ro crashkernel=auto net.ifnames=0 rhgb console=tty0 console=ttyS0,115200n8
grub_users $grub_users
grub_arg --unrestricted
grub_class fedora""",
            "/boot/loader/entries/0649288e52434223afde4c36460a375e-6.11.9-101.fc39.x86_64.conf": """title Fedora Linux (6.11.9-101.fc39.x86_64) 39 (Thirty Nine)
version 6.11.9-101.fc39.x86_64
linux /boot/vmlinuz-6.11.9-101.fc39.x86_64
initrd /boot/initramfs-6.11.9-101.fc39.x86_64.img
options root=UUID=a7e970a5-14fb-4a8a-ab09-603d1ac3fee9 ro crashkernel=auto net.ifnames=0 rhgb console=tty0 console=ttyS0,115200n8
grub_users $grub_users
grub_arg --unrestricted
grub_class fedora""",
        },
        [
            {
                "title": "Fedora Linux (6.11.9-100.fc39.x86_64) 39 (Thirty Nine)",
                "version": "6.11.9-100.fc39.x86_64",
                "linux": "/boot/vmlinuz-6.11.9-100.fc39.x86_64",
                "initrd": "/boot/initramfs-6.11.9-100.fc39.x86_64.img",
                "options": "root=UUID=a7e970a5-14fb-4a8a-ab09-603d1ac3fee9 ro crashkernel=auto net.ifnames=0 rhgb console=tty0 console=ttyS0,115200n8",
                "grub_users": "$grub_users",
                "grub_arg": "--unrestricted",
                "grub_class": "fedora",
            },
            {
                "title": "Fedora Linux (6.11.9-101.fc39.x86_64) 39 (Thirty Nine)",
                "version": "6.11.9-101.fc39.x86_64",
                "linux": "/boot/vmlinuz-6.11.9-101.fc39.x86_64",
                "initrd": "/boot/initramfs-6.11.9-101.fc39.x86_64.img",
                "options": "root=UUID=a7e970a5-14fb-4a8a-ab09-603d1ac3fee9 ro crashkernel=auto net.ifnames=0 rhgb console=tty0 console=ttyS0,115200n8",
                "grub_users": "$grub_users",
                "grub_arg": "--unrestricted",
                "grub_class": "fedora",
            },
        ]
    ),
    # one entry with extra newlines
    (
        {
            "/boot/loader/entries/0649288e52434223afde4c36460a375e-6.11.9-100.fc39.x86_64.conf": """title Fedora Linux (6.11.9-100.fc39.x86_64) 39 (Thirty Nine)
version 6.11.9-100.fc39.x86_64
linux /boot/vmlinuz-6.11.9-100.fc39.x86_64
initrd /boot/initramfs-6.11.9-100.fc39.x86_64.img
options root=UUID=a7e970a5-14fb-4a8a-ab09-603d1ac3fee9 ro crashkernel=auto net.ifnames=0 rhgb console=tty0 console=ttyS0,115200n8
grub_users $grub_users
grub_arg --unrestricted
grub_class fedora

""",
        },
        [
            {
                "title": "Fedora Linux (6.11.9-100.fc39.x86_64) 39 (Thirty Nine)",
                "version": "6.11.9-100.fc39.x86_64",
                "linux": "/boot/vmlinuz-6.11.9-100.fc39.x86_64",
                "initrd": "/boot/initramfs-6.11.9-100.fc39.x86_64.img",
                "options": "root=UUID=a7e970a5-14fb-4a8a-ab09-603d1ac3fee9 ro crashkernel=auto net.ifnames=0 rhgb console=tty0 console=ttyS0,115200n8",
                "grub_users": "$grub_users",
                "grub_arg": "--unrestricted",
                "grub_class": "fedora",
            },
        ]
    ),
    # one entry with comments
    (
        {
            "/boot/loader/entries/0649288e52434223afde4c36460a375e-6.11.9-100.fc39.x86_64.conf": """title Fedora Linux (6.11.9-100.fc39.x86_64) 39 (Thirty Nine)
# this is a very useful comment
version 6.11.9-100.fc39.x86_64
linux /boot/vmlinuz-6.11.9-100.fc39.x86_64
initrd /boot/initramfs-6.11.9-100.fc39.x86_64.img
options root=UUID=a7e970a5-14fb-4a8a-ab09-603d1ac3fee9 ro crashkernel=auto net.ifnames=0 rhgb console=tty0 console=ttyS0,115200n8
# this is another very useful comment
grub_users $grub_users
grub_arg --unrestricted
grub_class fedora""",
        },
        [
            {
                "title": "Fedora Linux (6.11.9-100.fc39.x86_64) 39 (Thirty Nine)",
                "version": "6.11.9-100.fc39.x86_64",
                "linux": "/boot/vmlinuz-6.11.9-100.fc39.x86_64",
                "initrd": "/boot/initramfs-6.11.9-100.fc39.x86_64.img",
                "options": "root=UUID=a7e970a5-14fb-4a8a-ab09-603d1ac3fee9 ro crashkernel=auto net.ifnames=0 rhgb console=tty0 console=ttyS0,115200n8",
                "grub_users": "$grub_users",
                "grub_arg": "--unrestricted",
                "grub_class": "fedora",
            },
        ]
    ),
))
def test_read_boot_entries(tmp_path, fake_tree, entries):
    make_fake_tree(tmp_path, fake_tree)
    assert osbuild_image_info.read_boot_entries(tmp_path / "boot") == entries


def test_read_default_target_ok(tmp_path):
    """
    Test the happy case when determinig the systemd default target
    """
    make_fake_tree(tmp_path, {
        "/usr/lib/systemd/system/multi-user.target": """#  SPDX-License-Identifier: LGPL-2.1-or-later
#
#  This file is part of systemd.
#
#  systemd is free software; you can redistribute it and/or modify it
#  under the terms of the GNU Lesser General Public License as published by
#  the Free Software Foundation; either version 2.1 of the License, or
#  (at your option) any later version.

[Unit]
Description=Multi-User System
Documentation=man:systemd.special(7)
Requires=basic.target
Conflicts=rescue.service rescue.target
After=basic.target rescue.service rescue.target
AllowIsolate=yes
"""
    })
    etc_systemd_system_dir = tmp_path / "etc/systemd/system"
    etc_systemd_system_dir.mkdir(parents=True)
    default_target_link = etc_systemd_system_dir / "default.target"
    default_target_link.symlink_to("/usr/lib/systemd/system/multi-user.target")

    assert osbuild_image_info.read_default_target(tmp_path) == "multi-user.target"


def test_read_default_target_none(tmp_path):
    """
    Test the case when when there is no default target set on the system
    """
    assert osbuild_image_info.read_default_target(tmp_path) == ""


# root is needed, because the script will bind mount the dir as read-only
@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_empty_report_fail(tmp_path):
    """
    Test that the main() exits with a non-zero exit code if the report is empty.
    """
    with pytest.raises(SystemExit) as e, patch("sys.argv", ["osbuild-image-info", str(tmp_path)]):
        osbuild_image_info.main()
    assert e.value.code == 1


def make_fake_iso(iso_tree, output_dir) -> str:
    iso_path = os.path.join(output_dir, "image.iso")
    subprocess.run(["mkisofs", "-o", iso_path, "-R", "-J", iso_tree], check=True)
    return iso_path


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_analyse_iso_fail_mount(tmp_path):
    # fake ISO that can't be mounted
    image_path = tmp_path / "image.iso"
    image_path.touch()

    with pytest.raises(
            subprocess.CalledProcessError,
            match=fr"^Command '\['mount', '-o', 'ro,loop', PosixPath\('{image_path}'\)"):
        osbuild_image_info.analyse_iso(image_path)


@pytest.mark.skipif(os.getuid() != 0, reason="root only")
def test_analyse_iso_fail_no_tarball(tmp_path):
    # ISO that can be mounted, but doesn't contain the liveimg.tar.gz
    iso_tree = tmp_path / "iso_tree"
    iso_tree.mkdir()
    # NB: The random file is added to the ISO, because in GH actions, the produced
    # ISO was not valid and was consistently failing to be mounted.
    random_file = iso_tree / "random_file"
    random_file.write_text("random content")

    image_path = make_fake_iso(iso_tree, tmp_path)

    with pytest.raises(
            subprocess.CalledProcessError,
            match=r"^Command '\['tar', '--selinux', '--xattrs', '--acls', '-x', '--auto-compress', '-f', '/tmp/\w+/liveimg.tar.gz"):
        osbuild_image_info.analyse_iso(image_path)
