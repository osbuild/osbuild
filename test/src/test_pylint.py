#
# Run `pylint` on all python sources.
#

import os
import subprocess

import pytest

from .. import test


@pytest.fixture(name="source_files")
def discover_source_files():

    # Evaluate whether `path` is a python file. This assumes that the file is
    # opened by the caller, anyway, hence it might invoke `file` to detect the
    # file type if in doubt.
    def is_python_script(path):
        if path.endswith(".py"):
            return True

        mime_valid = [
            "text/x-python",
            "text/x-script.python",
        ]

        mime_file = subprocess.check_output(
            [
                "file",
                "-bi",
                "--",
                path,
            ],
            encoding="utf-8",
        )

        return any(mime_file.startswith(v) for v in mime_valid)

    # Enumerate all repository files. This will invoke `git ls-tree` to list
    # all files. This also requires a temporary change of directory, since git
    # operates on the current directory and does not allow path arguments.
    def list_files(path):
        cwd = os.getcwd()
        os.chdir(path)
        files = subprocess.check_output(
            [
                "git",
                "ls-tree",
                "-rz",
                "--full-tree",
                "--name-only",
                "HEAD",
            ],
            encoding="utf-8",
        )
        os.chdir(cwd)

        files = files.split('\x00')
        return (os.path.join(path, f) for f in files)

    if not test.TestBase.have_test_checkout():
        pytest.skip("no test-checkout access")

    files = list_files(test.TestBase.locate_test_checkout())
    files = filter(is_python_script, files)
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


@pytest.mark.skipif(not test.TestBase.have_mypy(), reason="mypy not available")
def test_mypy():
    #
    # Run `mypy` on osbuild sources.
    #

    r = subprocess.run(["mypy", "osbuild/"], check=False)
    if r.returncode != 0:
        pytest.fail("mypy issues detected")


@pytest.mark.skipif(not test.TestBase.have_isort(), reason="isort not available")
def test_isort(source_files):
    #
    # Run `isort` on all python sources. We simply use `find` to locate
    # all `*.py` files, and then manually select the reverse-domain named
    # modules we have.
    #

    r = subprocess.run(["isort", "--check", "--diff"] + source_files, check=False)
    if r.returncode != 0:
        pytest.fail("isort issues detected")


@pytest.mark.skipif(not test.TestBase.have_autopep8(), reason="autopep8 not available")
def test_autopep8(source_files):
    r = subprocess.run(["autopep8-3", "--diff", "--exit-code"] + source_files, check=False)
    if r.returncode != 0:
        pytest.fail("autopep8 has detected changes (see diff)")
