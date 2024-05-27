import configparser
import json
import os
import pathlib
import socket
import subprocess as sp
import sys
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
    return sp.run(["/usr/bin/python3", "-c", "import libdnf5"], check=False).returncode == 0


def has_dnf():
    return sp.run(["/usr/bin/python3", "-c", "import libdnf"], check=False).returncode == 0


def depsolve(pkgs, repos, root_dir, cache_dir, opt_metadata, command):
    req = {
        "command": "depsolve",
        "arch": ARCH,
        "module_platform_id": "platform:el9",
        "releasever": RELEASEVER,
        "cachedir": cache_dir,
        "arguments": {
            "root_dir": root_dir,
            "repos": repos,
            "optional-metadata": opt_metadata,
            "transactions": [
                {
                    "package-specs": pkgs,
                    "exclude-specs": None
                },
            ]
        }
    }
    p = sp.run([command], input=json.dumps(req).encode(), check=True, stdout=sp.PIPE, stderr=sys.stderr)

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
        p = sp.Popen(["python3", "-m", "http.server", str(port)], cwd=path, stdout=sp.PIPE, stderr=sp.DEVNULL)
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


def make_dnf_scafolding(base_dir):
    root_dir = pathlib.Path(TemporaryDirectory(dir=base_dir).name)

    repos_dir = root_dir / "etc/yum.repos.d"
    repos_dir.mkdir(parents=True)
    keys_dir = root_dir / "etc/pki/rpm-gpg"
    keys_dir.mkdir(parents=True)
    vars_dir = root_dir / "etc/dnf/vars"
    vars_dir.mkdir(parents=True)

    vars_path = vars_dir / "customvar"
    vars_path.write_text(CUSTOMVAR, encoding="utf8")

    return root_dir, repos_dir, keys_dir


def config_combos(tmp_path, servers):
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
                "sslverify": False,
                "rhsm": False,
                "gpgkeys": [TEST_KEY + server["name"]],
            })
        root_dir, repos_dir, keys_dir = make_dnf_scafolding(tmp_path)
        for idx in combo[1]:  # servers to be configured through root_dir
            server = servers[idx]
            name = server["name"]
            # Use the gpgkey to test both the key reading and the variable substitution.
            # For this test, it doesn't need to be a real key.
            key_url = f"file:///etc/pki/rpm-gpg/RPM-GPG-KEY-$releasever-$basearch-$customvar-{name}"

            key_path = keys_dir / f"RPM-GPG-KEY-{RELEASEVER}-{ARCH}-{CUSTOMVAR}-{name}"
            key_path.write_text(TEST_KEY + name, encoding="utf8")
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

            with (repos_dir / f"{name}.repo").open("w", encoding="utf-8") as fp:
                parser.write(fp, space_around_delimiters=False)

        # for each combo, let's also enable or disable filelists (optional-metadata)
        for opt_metadata in ([], ["filelists"]):
            yield repo_configs, os.fspath(root_dir), opt_metadata


@pytest.mark.parametrize("test_case", test_cases)
@pytest.mark.parametrize("dnf_cmd, detect_fn", [
    ("./tools/osbuild-depsolve-dnf", has_dnf),
    ("./tools/osbuild-depsolve-dnf5", has_dnf5),
])
def test_depsolve(tmp_path, repo_servers, dnf_cmd, detect_fn, test_case):
    if not detect_fn():
        pytest.skip(f"cannot import support for {dnf_cmd}")

    pks = test_case["packages"]

    for repo_configs, root_dir, opt_metadata in config_combos(tmp_path, repo_servers):
        with TemporaryDirectory() as cache_dir:
            res = depsolve(pks, repo_configs, root_dir, cache_dir, opt_metadata, dnf_cmd)
            assert {pkg["name"] for pkg in res["packages"]} == test_case["results"]["packages"]
            assert res["repos"].keys() == test_case["results"]["reponames"]
            for repo in res["repos"].values():
                assert repo["gpgkeys"] == [TEST_KEY + repo["id"]]
                assert repo["sslverify"] is False
