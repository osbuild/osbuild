#
# Tests for the 'osbuild.util.path' module
#
import os

from osbuild.util import path

def test_in_tree():
    cases = {
        ("/tmp/file", "/tmp", False): True,  # Simple, non-existent
        ("/etc", "/", True): True,  # Simple, should exist
        ("/tmp/../../file", "/tmp", False): False,  # Relative path escape
        ("/very/fake/directory/and/file", "/very", False): True,  # non-existent, OK
        ("/very/fake/directory/and/file", "/very", True): False,  # non-existent, not-OK
        ("../..", os.path.abspath("."), False): False,  # Relative path escape from cwd
        (".", os.path.abspath("../.."), False): True,  # cwd inside parent of parent
    }

    for args, expected in cases.items():
        assert path.in_tree(*args) == expected, args
