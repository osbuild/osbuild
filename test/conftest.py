import pathlib
import tempfile

import pytest

unsupported_filesystems = []
"""Globally accessible list of filesystems that are unsupported on the system when running test cases"""


def pytest_addoption(parser):
    parser.addoption(
        "--unsupported-fs",
        action="append",
        default=[],
        metavar="FS",
        help="List of filesystems to treat as unsupported on the system when running test cases." +
             "Can be specified multiple times.",
    )


def pytest_configure(config):
    # pylint: disable=global-statement
    global unsupported_filesystems
    unsupported_filesystems = config.getoption("--unsupported-fs")


# overriding the build-in "tmp_path" to use /var/tmp because
# /tmp is often of limited size (e.g.tmpfs) and our tests
# produce large amounts of data
@pytest.fixture(name="tmp_path")
def tmp_path_fixture():
    with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
        yield pathlib.Path(tmp)
