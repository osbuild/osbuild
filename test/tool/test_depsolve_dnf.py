import json
import os
import subprocess

import pytest

DEPSOLVE_DNF_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "tools",
        "osbuild-depsolve-dnf",
    )
)


def test_depsolve_dnf_no_stdin():
    assert subprocess.run([DEPSOLVE_DNF_PATH]).returncode == 1
