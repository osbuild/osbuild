#
# Run `pylint` on all python sources.
#

import os
import subprocess

import pytest

from .. import test


@pytest.fixture(name="source_files")
def discover_source_files():
    if not test.TestBase.have_test_checkout():
        pytest.skip("no test-checkout access")

    checkout = test.TestBase.locate_test_checkout()

    # Fetch list of checked-in files from git.
    cwd = os.getcwd()
    os.chdir(checkout)
    files = subprocess.check_output(
        [
            "git",
            "ls-tree",
            "-rz",
            "--full-tree",
            "--name-only",
            "HEAD",
        ]
    ).decode()
    os.chdir(cwd)

    # File list is separated by NULs, so split into array.
    files = files.split('\x00')

    # Filter out all our python files (i.e., all modules and files ending in *.py)
    modules = ("assemblers/", "runners/", "sources/", "stages/")
    files = filter(lambda p: p.endswith(".py") or p.startswith(modules), files)

    # Append the checkout-path so all paths are absolute.
    files = map(lambda p: os.path.join(checkout, p), files)

    return list(files)


def test_pylint(source_files):
    #
    # Run `pylint` on all python sources. We simply use `find` to locate
    # all `*.py` files, and then manually select the reverse-domain named
    # modules we have.
    #

    r = subprocess.run(["pylint"] + source_files, check=False)
    if r.returncode != 0:
        pytest.fail("pylint issues detected")


@pytest.mark.skipif(not test.TestBase.have_autopep8(), reason="autopep8 not available")
def test_autopep8(source_files):
    r = subprocess.run(["autopep8-3", "--diff", "--exit-code"] + source_files, check=False)
    if r.returncode != 0:
        pytest.fail("autopep8 has detected changes (see diff)")
