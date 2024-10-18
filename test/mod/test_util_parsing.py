"""Unit tests for osbuild.util.parsing"""

import pytest

from osbuild.util import parsing


def test_parse_size():
    cases = [
        ("123", True, 123),
        ("123 kB", True, 123000),
        ("123 KiB", True, 123 * 1024),
        ("123 MB", True, 123 * 1000 * 1000),
        ("123 MiB", True, 123 * 1024 * 1024),
        ("123 GB", True, 123 * 1000 * 1000 * 1000),
        ("123 GiB", True, 123 * 1024 * 1024 * 1024),
        ("123 TB", True, 123 * 1000 * 1000 * 1000 * 1000),
        ("123 TiB", True, 123 * 1024 * 1024 * 1024 * 1024),
        ("123kB", True, 123000),
        ("123KiB", True, 123 * 1024),
        (" 123", True, 123),
        ("  123kB", True, 123000),
        ("  123KiB", True, 123 * 1024),
        ("unlimited", True, "unlimited"),
        ("string", False, 0),
        ("123 KB", False, 0),
        ("123 mb", False, 0),
        ("123 PB", False, 0),
        ("123 PiB", False, 0),

    ]

    for s, success, num in cases:
        if not success:
            with pytest.raises(TypeError):
                parsing.parse_size(s)
        else:
            res = parsing.parse_size(s)
            assert res == num, f"{s} parsed as {res} (wanted {num})"


def test_parse_location_mounts():
    args = {
        "paths": {
            "mounts": "/run/osbuild/mounts",
        },
        "mounts": {
            "root": {
                "path": "/run/osbuild/mounts/.",
            },
            "boot": {
                "path": "/run/osbuild/mounts/boot"
            }
        },
    }
    location = "mount://root/"
    root, path = parsing.parse_location_into_parts(location, args)
    assert [root, path] == ["/run/osbuild/mounts/.", "/"]
    path = parsing.parse_location(location, args)
    assert path == "/run/osbuild/mounts/."

    location = "mount://boot/efi/EFI/Linux"
    root, path = parsing.parse_location_into_parts(location, args)
    assert [root, path] == ["/run/osbuild/mounts/boot", "/efi/EFI/Linux"]
    path = parsing.parse_location(location, args)
    assert path == "/run/osbuild/mounts/boot/efi/EFI/Linux"


def test_parse_location_tree():
    args = {
        "tree": "/run/osbuild/tree",
    }
    location = "tree:///disk.img"
    root, path = parsing.parse_location_into_parts(location, args)
    assert [root, path] == ["/run/osbuild/tree", "/disk.img"]
    path = parsing.parse_location(location, args)
    assert path == "/run/osbuild/tree/disk.img"


def test_parse_location_inputs():
    args = {
        "inputs": {
            "tree": {
                "path": "/run/osbuild/inputs/tree",
            },
        },
    }
    location = "input://tree/"
    root, path = parsing.parse_location_into_parts(location, args)
    assert [root, path] == ["/run/osbuild/inputs/tree", "/"]
    path = parsing.parse_location(location, args)
    assert path == "/run/osbuild/inputs/tree/."
