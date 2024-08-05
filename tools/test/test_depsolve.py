import configparser
import json
import os
import pathlib
import re
import socket
import subprocess as sp
import sys
from glob import glob
from itertools import combinations
from tempfile import TemporaryDirectory
from typing import Tuple

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


def assert_dnf5():
    if sp.run(["/usr/bin/python3", "-c", "import libdnf5"], check=False).returncode != 0:
        raise RuntimeError("Cannot import libdnf5")


def assert_dnf():
    if sp.run(["/usr/bin/python3", "-c", "import libdnf"], check=False).returncode != 0:
        raise RuntimeError("Cannot import libdnf")


def depsolve(transactions, repos, root_dir, cache_dir, dnf_config, opt_metadata) -> Tuple[dict, int]:
    req = {
        "command": "depsolve",
        "arch": ARCH,
        "module_platform_id": f"platform:el{RELEASEVER}",
        "releasever": RELEASEVER,
        "cachedir": cache_dir,
        "arguments": {
            "root_dir": root_dir,
            "repos": repos,
            "optional-metadata": opt_metadata,
            "transactions": transactions,
        }
    }

    # If there is a config file, write it to a temporary file and pass it to the depsolver
    with TemporaryDirectory() as cfg_dir:
        env = None
        if dnf_config:
            cfg_file = pathlib.Path(cfg_dir) / "solver.json"
            cfg_file.write_text(dnf_config)
            env = {"OSBUILD_SOLVER_CONFIG": os.fspath(cfg_file)}

        p = sp.run(["./tools/osbuild-depsolve-dnf"], input=json.dumps(req), env=env,
                   check=False, stdout=sp.PIPE, stderr=sys.stderr, universal_newlines=True)

        return json.loads(p.stdout), p.returncode


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


def tcase_idfn(param):
    return param['id']


test_cases = [
    {
        "id": "basic_1pkg_1repo",
        "transactions": [
            {
                "package-specs": [
                    "filesystem",
                ],
            },
        ],
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
    # "pkg-with-no-deps" is the only package in the custom repo and has no dependencies
    {
        "id": "basic_1pkg_1repo_no_deps",
        "transactions": [
            {
                "package-specs": [
                    "pkg-with-no-deps",
                ],
            },
        ],
        "results": {
            "packages": {"pkg-with-no-deps"},
            "reponames": {"custom"},
        },
    },
    {
        "id": "basic_2pkgs_2repos",
        "transactions": [
            {
                "package-specs": [
                    "filesystem",
                    "pkg-with-no-deps"
                ],
            },
        ],
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
    # Test depsolving error due to non-existing package
    {
        "id": "error_non_existing_pkg",
        "transactions": [
            {
                "package-specs": [
                    "non-existing-package",
                ],
            },
        ],
        "error": True,
        "error_kind": "MarkingErrors",
        "error_reason_re": r".*non-existing-package.*",
    },
    # Test depsolving error due to conflicting packages
    {
        "id": "error_conflicting_pkgs",
        "transactions": [
            {
                "package-specs": [
                    "curl",
                    "curl-minimal",
                ],
            },
        ],
        "error": True,
        "error_kind": "DepsolveError",
        "error_reason_re": r".*package curl-minimal-.*\.el9\.x86_64.*conflicts with curl provided by curl-.*\.el9\.x86_64.*",
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


def gen_config_combos(items_count):
    """
    Generate all possible combinations of indexes of items_count items
    into two disjoint groups.
    """
    indexes = list(range(items_count))
    all_combinations = []

    for combination_length in range(items_count + 1):
        for combo_set in combinations(indexes, combination_length):
            combo_complement_set = tuple(i for i in indexes if i not in combo_set)
            all_combinations.append((combo_set, combo_complement_set))

    return all_combinations


@pytest.mark.parametrize("items_count,expected_combos", (
    (0, [((), ())]),
    (1, [
        ((), (0,)),
        ((0,), ()),
    ]),
    (2, [
        ((), (0, 1)),
        ((0,), (1,)),
        ((1,), (0,)),
        ((0, 1), ()),
    ]),
    (3, [
        ((), (0, 1, 2)),
        ((0,), (1, 2)),
        ((1,), (0, 2)),
        ((2,), (0, 1)),
        ((0, 1), (2,)),
        ((0, 2), (1,)),
        ((1, 2), (0,)),
        ((0, 1, 2), ())
    ])
))
def test_gen_config_combos(items_count, expected_combos):
    assert list(gen_config_combos(items_count)) == expected_combos


def config_combos(tmp_path, servers):
    """
    Return all configurations for the provided repositories, either as config files in a directory or as repository
    configs in the depsolve request, or a combination of both.
    """
    for combo in gen_config_combos(len(servers)):
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


@pytest.mark.parametrize("test_case", test_cases, ids=tcase_idfn)
@pytest.mark.parametrize("dnf_config, detect_fn", [
    (None, assert_dnf),
    ('{"use_dnf5": false}', assert_dnf),
    ('{"use_dnf5": true}', assert_dnf5),
], ids=["no-config", "dnf4", "dnf5"])
def test_depsolve(tmp_path, repo_servers, dnf_config, detect_fn, test_case):
    try:
        detect_fn()
    except RuntimeError as e:
        pytest.skip(e)

    transactions = test_case["transactions"]

    for repo_configs, root_dir, opt_metadata in config_combos(tmp_path, repo_servers):
        with TemporaryDirectory() as cache_dir:
            res, exit_code = depsolve(transactions, repo_configs, root_dir, cache_dir, dnf_config, opt_metadata)

            if test_case.get("error", False):
                assert exit_code != 0
                assert res["kind"] == test_case["error_kind"]
                assert re.match(test_case["error_reason_re"], res["reason"], re.DOTALL)
                continue

            assert exit_code == 0
            assert {pkg["name"] for pkg in res["packages"]} == test_case["results"]["packages"]
            assert res["repos"].keys() == test_case["results"]["reponames"]
            for repo in res["repos"].values():
                assert repo["gpgkeys"] == [TEST_KEY + repo["id"]]
                assert repo["sslverify"] is False

            # if opt_metadata includes 'filelists', then each repository 'repodata' must include a file that matches
            # *filelists*
            n_filelist_files = len(glob(f"{cache_dir}/*/repodata/*filelists*"))
            if "filelists" in opt_metadata:
                assert n_filelist_files == len(REPO_PATHS)
            else:
                assert n_filelist_files == 0

            if dnf_config:
                use_dnf5 = json.loads(dnf_config)["use_dnf5"]
            else:
                use_dnf5 = False
            if use_dnf5:
                assert res["solver"] == "dnf5"
            else:
                assert res["solver"] == "dnf"
