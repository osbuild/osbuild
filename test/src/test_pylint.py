#
# Run `pylint` on all python sources.
#

import os
import subprocess

import pytest

from .. import test


@pytest.mark.skipif(not test.TestBase.have_test_checkout(), "no test-checkout access")
def test_pylint():
    #
    # Run `pylint` on all python sources. We simply use `find` to locate
    # all `*.py` files, and then manually select the reverse-domain named
    # modules we have.
    #

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

    # Run pylint on all files.
    subprocess.run(["pylint"] + list(files), check=True)
