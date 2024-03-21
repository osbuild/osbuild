import json
import os
import socket
import subprocess as sp

import pytest

REPO_PATHS = [
    "./test/data/testrepos/baseos/",
    "./test/data/testrepos/custom/",
]


def depsolve(pkgs, repos, repos_dir):
    req = {
        "command": "depsolve",
        "arch": "x86_64",
        "module_platform_id": "platform:el9",
        "cachedir": "/tmp/rpmmd",
        "arguments": {
            "repos_dir": repos_dir,
            "repos": repos,
            "transactions": [
                {"package-specs": pkgs},
            ]
        }
    }
    p = sp.run(["./tools/osbuild-depsolve-dnf"], input=json.dumps(req).encode(), check=True, capture_output=True)
    if p.stderr:
        print(p.stderr.decode())

    return json.loads(p.stdout.decode())


def get_rand_port():
    s = socket.socket()
    s.bind(("", 0))
    return s.getsockname()[1]


@pytest.fixture(name="repo_servers")
def repo_servers_fixture():
    procs = []
    addresses = []
    for path in REPO_PATHS:
        port = get_rand_port()  # this is racy, but should be okay
        p = sp.Popen(["python3", "-m", "http.server", str(port)], cwd=path, stdout=sp.PIPE)
        procs.append(p)
        # use last path component as name
        name = os.path.basename(path.rstrip("/"))
        addresses.append({"name": name, "address": f"http://localhost:{port}"})
    yield addresses
    for p in procs:
        p.kill()


test_cases = [
    {
        "packages": ["filesystem"],
        "results": {
            "basesystem",
            "bash",
            "centos-gpg-keys",
            "centos-stream-release",
            "centos-stream-repos",
            "filesystem",
            "glibc",
            "glibc-common",
            "glibc-minimal-langpack",
            "libgcc",
            "ncurses-base",
            "ncurses-libs",
            "setup",
            "tzdata",
        }
    }
]


@pytest.mark.parametrize("test_case", test_cases)
def test_depsolve(repo_servers, test_case):
    pks = test_case["packages"]

    repo_configs = []
    for server in repo_servers:
        repo_configs.append({
            "id": server["name"],
            "name": server["name"],
            "baseurl": server["address"],
            "check_gpg": False,
            "ignoressl": True,
            "rhsm": False,
        })
    res = depsolve(pks, repo_configs, test_case.get("repos_dir"))
    assert {pkg["name"] for pkg in res} == test_case["results"]
