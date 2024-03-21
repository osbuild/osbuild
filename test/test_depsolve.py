import configparser
import json
import os
import socket
import subprocess as sp
from tempfile import TemporaryDirectory

import pytest

REPO_PATHS = [
    "./test/data/testrepos/baseos/",
    "./test/data/testrepos/custom/",
]


def depsolve(pkgs, repos, repos_dir, cache_dir):
    req = {
        "command": "depsolve",
        "arch": "x86_64",
        "module_platform_id": "platform:el9",
        "cachedir": cache_dir,
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


@pytest.fixture(name="repo_servers", scope="module")
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
    },
    {
        # "nothing" is the only package in the custom repo and has no dependencies
        "packages": ["nothing"],
        "results": {
            "nothing",
        }
    },
    {
        "packages": ["filesystem", "nothing"],
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
            "nothing"
        }
    },
    {
        "packages": ["tmux", "nothing"],
        "results": {
            "alternatives",
            "basesystem",
            "bash",
            "ca-certificates",
            "centos-gpg-keys",
            "centos-stream-release",
            "centos-stream-repos",
            "coreutils",
            "coreutils-common",
            "crypto-policies",
            "filesystem",
            "glibc",
            "glibc-common",
            "glibc-minimal-langpack",
            "gmp",
            "grep",
            "libacl",
            "libattr",
            "libcap",
            "libevent",
            "libffi",
            "libgcc",
            "libselinux",
            "libsepol",
            "libsigsegv",
            "libtasn1",
            "ncurses-base",
            "ncurses-libs",
            "openssl-libs",
            "p11-kit",
            "p11-kit-trust",
            "pcre",
            "pcre2",
            "pcre2-syntax",
            "sed",
            "setup",
            "tmux",
            "tzdata",
            "zlib",
            "nothing",
        }
    },
]


def config_combos(servers):
    """
    Return all configurations for the provided repositories, either as config files in a directory or as repository
    configs in the depsolve request, or a combination of both.
    """
    # we only have two servers, so let's just enumerate all the combinations
    combo_idxs = [
        ((0, 1), ()),  # all in req
        ((0,), (1,)),    # one in req and one in dir
        ((1,), (0,)),    # same but flipped
        ((), (0, 1)),  # all in dir
    ]
    for combo in combo_idxs:
        repo_configs = []
        for idx in combo[0]:  # servers to be configured through request
            server = servers[idx]
            repo_configs.append({
                "id": server["name"],
                "name": server["name"],
                "baseurl": server["address"],
                "check_gpg": False,
                "ignoressl": True,
                "rhsm": False,
            })
        with TemporaryDirectory() as repos_dir:
            for idx in combo[1]:  # servers to be configured through repos_dir
                server = servers[idx]
                parser = configparser.ConfigParser()
                name = server["name"]
                parser.add_section(name)
                # Set some options in a specific order in which they tend to be
                # written in repo files.
                parser.set(name, "name", name)
                parser.set(name, "baseurl", server["address"])
                parser.set(name, "enabled", "1")
                parser.set(name, "gpgcheck", "0")
                parser.set(name, "sslverify", "0")

                with open(f"{repos_dir}/{name}.repo", "w", encoding="utf-8") as repo_file:
                    parser.write(repo_file, space_around_delimiters=False)

            yield repo_configs, repos_dir


@pytest.fixture(name="cache_dir", scope="session")
def cache_dir_fixture(tmpdir_factory):
    return str(tmpdir_factory.mktemp("cache"))


@pytest.mark.parametrize("test_case", test_cases)
def test_depsolve(repo_servers, test_case, cache_dir):
    pks = test_case["packages"]

    for repo_configs, repos_dir in config_combos(repo_servers):
        res = depsolve(pks, repo_configs, repos_dir, cache_dir)
        assert {pkg["name"] for pkg in res} == test_case["results"]
