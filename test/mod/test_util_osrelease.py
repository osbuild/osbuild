#
# Tests for the `osbuild.util.osrelease` module.
#

import os
import unittest

import pytest

from osbuild.util import osrelease

from .. import test


class TestUtilOSRelease(test.TestBase):
    def test_non_existant(self):
        #
        # Verify default os-release value, if no files are given.
        #

        self.assertEqual(osrelease.describe_os(), "linux")

    @unittest.skipUnless(test.TestBase.have_test_data(), "no test-data access")
    def test_describe_os(self):
        #
        # Test host os detection. test/os-release contains the os-release files
        # for all supported runners.
        #

        for entry in os.scandir(os.path.join(self.locate_test_data(), "os-release")):
            with self.subTest(entry.name):
                self.assertEqual(osrelease.describe_os(entry.path), entry.name)


def test_osreleae_f40_really_coreos_happy():
    here = os.path.dirname(__file__)
    res = osrelease.parse_files(os.path.join(here, "../data/os-release/fedora40"))
    assert res["NAME"] == 'Fedora Linux'
    assert res["ID"] == 'fedora'
    assert res["OSTREE_VERSION"] == '40.20241106.dev.0'


@pytest.mark.parametrize("content,expected_err", [
    ("OSTREE=", "Key 'OSTREE' has an empty value"),
    ("OSTREE='foo' 'bar'", "Key 'OSTREE' has more than one token: 'foo' 'bar'"),
])
def test_osrelease_bad_split_empty(tmp_path, content, expected_err):
    bad_os_release_path = tmp_path / "os-release"
    bad_os_release_path.write_text(content + "\n")
    with pytest.raises(ValueError) as exc:
        osrelease.parse_files(bad_os_release_path)
    assert str(exc.value) == expected_err
