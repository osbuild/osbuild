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


@pytest.mark.parametrize(
    "data,reason",
    [
        ({}, "invalid command"),
        ({"command": "depsolve"}, "no 'arch' specified"),
        ({"command": "non-existent"}, "invalid command"),
        (
            {"command": "depsolve", "arch": "x86_64"},
            "no 'module_platform_id' specified",
        ),
        # note, we could perhaps test arch availability and provide a better error
        # message here
        (
            {"command": "depsolve", "arch": "non-existent"},
            "no 'module_platform_id' specified",
        ),
        (
            {
                "command": "depsolve",
                "arch": "x86_64",
                "module_platform_id": "f39",
            },
            "empty 'arguments'",
        ),
        # note, we could perhaps test module platform id availability and provide a
        # better error message here
        (
            {
                "command": "depsolve",
                "arch": "x86_64",
                "module_platform_id": "non-existent",
            },
            "empty 'arguments'",
        ),
        (
            {
                "command": "depsolve",
                "arch": "x86_64",
                "module_platform_id": "f39",
                "args": {},
            },
            "empty 'arguments'",
        ),
    ],
)
def test_depsolve_dnf_partial_request_errors(data, reason):
    proc = subprocess.run(
        [DEPSOLVE_DNF_PATH],
        input=json.dumps(data),
        encoding="utf8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert proc.returncode == 1

    response = json.loads(proc.stdout)

    assert reason in response["reason"]
