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
