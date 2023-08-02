#
# Test for the util.checksum module
#
from tempfile import NamedTemporaryFile

import pytest

from osbuild.util import checksum

# pylint: disable=line-too-long
TEST_STRING = "I have of late, but wherefore I know not, lost all my bytes\n"
TEST_RESULT = {
    "md5": "537f2c2e965f5ce9c524704b58cb7660",
    "sha1": "897b9791e74e937fccc885e093897a071c2a54fb",
    "sha256": "16bf29978fc76774eef051739e1e9e9983bcb29285250ffddfc1955f8a3f95fb",
    "sha384": "7f7c72cabd9af1872e22713efe02deb6234475affcc6b8c9816ce683fee2f63285b466880171f462d49fbefb0dd35ee6",
    "sha512": "f0874cb102032ca78070c07fd4a894c3eb752b903ab758a54aa8937b2a77830bac40f1faf8ae0e206ff56c4446699a2ae4941f4a6d6556cab4a4ac072216bacc",
}


@pytest.fixture(name="tempfile")
def tempfile_fixture():
    with NamedTemporaryFile(prefix="verify-file-", mode="w") as f:
        yield f


@pytest.mark.parametrize("algorithm", TEST_RESULT.keys())
def test_verify_file(algorithm, tempfile):
    tempfile.write(TEST_STRING)
    tempfile.flush()

    digest = TEST_RESULT[algorithm]
    full_digest = f"{algorithm}:{digest}"
    assert checksum.verify_file(tempfile.name, full_digest), "checksums mismatch"
