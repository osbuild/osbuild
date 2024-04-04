import configparser
import importlib
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

RELEASEVER = "9"
ARCH = "x86_64"
CUSTOMVAR = "test"

# osbuild-depsolve-dnf uses the GPG header to detect if keys are defined in-line or as file paths/URLs
TEST_KEY = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nTEST KEY\n"


def has_dnf5():
    return bool(importlib.util.find_spec("libdnf5"))


def depsolve(pkgs, repos, root_dir, cache_dir, command):
    req = {
        "command": "depsolve",
        "arch": ARCH,
        "module_platform_id": "platform:el9",
        "releasever": RELEASEVER,
        "cachedir": cache_dir,
        "arguments": {
            "root_dir": root_dir,
            "repos": repos,
            "transactions": [
                {"package-specs": pkgs},
            ]
        }
    }
    p = sp.run([command], input=json.dumps(req).encode(), check=True, capture_output=True)
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
            "packages": {
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
            },
            "reponames": {
                "baseos",
            },
        }
    },
    {
        # "pkg-with-no-deps" is the only package in the custom repo and has no dependencies
        "packages": ["pkg-with-no-deps"],
        "results": {
            "packages": {"pkg-with-no-deps"},
            "reponames": {"custom"},
        },
    },
    {
        "packages": ["filesystem", "pkg-with-no-deps"],
        "results": {
            "packages": {
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
                "pkg-with-no-deps",
            },
            "reponames": {
                "baseos",
                "custom",
            },
        },
    },
    {
        "packages": ["tmux", "pkg-with-no-deps"],
        "results": {
            "packages": {
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
                "pkg-with-no-deps",
            },
            "reponames": {
                "baseos",
                "custom",
            },
        },
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
                "gpgkeys": [TEST_KEY + server["name"]],
            })
        with TemporaryDirectory() as root_dir:
            repos_dir = os.path.join(root_dir, "etc/yum.repos.d")
            os.makedirs(repos_dir)
            keys_dir = os.path.join(root_dir, "etc/pki/rpm-gpg")
            os.makedirs(keys_dir)
            vars_dir = os.path.join(root_dir, "etc/dnf/vars")
            os.makedirs(vars_dir)

            vars_path = os.path.join(vars_dir, "customvar")
            with open(vars_path, "w", encoding="utf-8") as vars_file:
                vars_file.write(CUSTOMVAR)

            for idx in combo[1]:  # servers to be configured through root_dir
                server = servers[idx]
                name = server["name"]
                # Use the gpgkey to test both the key reading and the variable substitution.
                # For this test, it doesn't need to be a real key.
                key_url = f"file:///etc/pki/rpm-gpg/RPM-GPG-KEY-$releasever-$basearch-$customvar-{name}"

                key_path = os.path.join(keys_dir, f"RPM-GPG-KEY-{RELEASEVER}-{ARCH}-{CUSTOMVAR}-{name}")
                with open(key_path, "w", encoding="utf-8") as key_file:
                    key_file.write(TEST_KEY + name)
                parser = configparser.ConfigParser()
                parser.add_section(name)
                # Set some options in a specific order in which they tend to be
                # written in repo files.
                parser.set(name, "name", name)
                parser.set(name, "baseurl", server["address"])
                parser.set(name, "enabled", "1")
                parser.set(name, "gpgcheck", "1")
                parser.set(name, "sslverify", "0")
                parser.set(name, "gpgkey", key_url)

                with open(f"{repos_dir}/{name}.repo", "w", encoding="utf-8") as repo_file:
                    parser.write(repo_file, space_around_delimiters=False)

            yield repo_configs, root_dir


@pytest.fixture(name="cache_dir", scope="session")
def cache_dir_fixture(tmpdir_factory):
    return str(tmpdir_factory.mktemp("cache"))


@pytest.mark.parametrize("test_case", test_cases)
def test_depsolve(repo_servers, test_case, cache_dir):
    pks = test_case["packages"]

    for repo_configs, root_dir in config_combos(repo_servers):
        res = depsolve(pks, repo_configs, root_dir, cache_dir, "./tools/osbuild-depsolve-dnf")
        assert {pkg["name"] for pkg in res["packages"]} == test_case["results"]["packages"]
        assert res["repos"].keys() == test_case["results"]["reponames"]
        for repo in res["repos"].values():
            assert repo["gpgkeys"] == [TEST_KEY + repo["id"]]


@pytest.mark.skipif(not has_dnf5(), reason="libdnf5 not available")
@pytest.mark.parametrize("test_case", test_cases)
def test_depsolve_dnf5(repo_servers, test_case, cache_dir):
    pks = test_case["packages"]

    for repo_configs, repos_dir in config_combos(repo_servers):
        res = depsolve(pks, repo_configs, repos_dir, cache_dir, "./tools/osbuild-depsolve-dnf5")
        assert {pkg["name"] for pkg in res["packages"]} == test_case["results"]["packages"]
        assert res["repos"].keys() == test_case["results"]["reponames"]
        for repo in res["repos"].values():
            assert repo["gpgkeys"] == [TEST_KEY + repo["id"]]
