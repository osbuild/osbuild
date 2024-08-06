# pylint: disable=too-many-lines

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


def dump(repos, root_dir, cache_dir, dnf_config, opt_metadata) -> Tuple[dict, int]:
    req = {
        "command": "dump",
        "arch": ARCH,
        "module_platform_id": f"platform:el{RELEASEVER}",
        "releasever": RELEASEVER,
        "cachedir": cache_dir,
        "arguments": {
            "root_dir": root_dir,
            "repos": repos,
            "optional-metadata": opt_metadata,
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


def search(search_args, repos, root_dir, cache_dir, dnf_config, opt_metadata) -> Tuple[dict, int]:
    req = {
        "command": "search",
        "arch": ARCH,
        "module_platform_id": f"platform:el{RELEASEVER}",
        "releasever": RELEASEVER,
        "cachedir": cache_dir,
        "arguments": {
            "search": search_args,
            "root_dir": root_dir,
            "repos": repos,
            "optional-metadata": opt_metadata,
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


depsolve_test_cases = [
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
    {
        "id": "basic_pkg_group",
        "transactions": [
            {
                "package-specs": [
                    "@core",
                ],
            },
        ],
        "results": {
            "packages": {
                "acl",
                "alternatives",
                "attr",
                "audit",
                "audit-libs",
                "authselect",
                "authselect-libs",
                "basesystem",
                "bash",
                "binutils",
                "binutils-gold",
                "bzip2-libs",
                "ca-certificates",
                "c-ares",
                "centos-gpg-keys",
                "centos-stream-release",
                "centos-stream-repos",
                "coreutils",
                "coreutils-common",
                "cpio",
                "cracklib",
                "cracklib-dicts",
                "cronie",
                "cronie-anacron",
                "crontabs",
                "crypto-policies",
                "crypto-policies-scripts",
                "cryptsetup-libs",
                "curl",
                "cyrus-sasl-lib",
                "dbus",
                "dbus-broker",
                "dbus-common",
                "dbus-libs",
                "device-mapper",
                "device-mapper-libs",
                "diffutils",
                "dnf",
                "dnf-data",
                "dnf-plugins-core",
                "dracut",
                "dracut-config-rescue",
                "dracut-network",
                "dracut-squash",
                "e2fsprogs",
                "e2fsprogs-libs",
                "elfutils-debuginfod-client",
                "elfutils-default-yama-scope",
                "elfutils-libelf",
                "elfutils-libs",
                "ethtool",
                "expat",
                "file",
                "file-libs",
                "filesystem",
                "findutils",
                "firewalld",
                "firewalld-filesystem",
                "fuse-libs",
                "gawk",
                "gdbm-libs",
                "gettext",
                "gettext-libs",
                "glib2",
                "glibc",
                "glibc-common",
                "glibc-minimal-langpack",
                "gmp",
                "gnupg2",
                "gnutls",
                "gobject-introspection",
                "gpgme",
                "grep",
                "groff-base",
                "grub2-common",
                "grub2-tools",
                "grub2-tools-minimal",
                "grubby",
                "gzip",
                "hostname",
                "hwdata",
                "ima-evm-utils",
                "inih",
                "initscripts-rename-device",
                "initscripts-service",
                "iproute",
                "iproute-tc",
                "ipset",
                "ipset-libs",
                "iptables-libs",
                "iptables-nft",
                "iputils",
                "irqbalance",
                "iwl1000-firmware",
                "iwl100-firmware",
                "iwl105-firmware",
                "iwl135-firmware",
                "iwl2000-firmware",
                "iwl2030-firmware",
                "iwl3160-firmware",
                "iwl5000-firmware",
                "iwl5150-firmware",
                "iwl6000g2a-firmware",
                "iwl6050-firmware",
                "iwl7260-firmware",
                "jansson",
                "jq",
                "json-c",
                "kbd",
                "kbd-legacy",
                "kbd-misc",
                "kernel-tools",
                "kernel-tools-libs",
                "kexec-tools",
                "keyutils",
                "keyutils-libs",
                "kmod",
                "kmod-libs",
                "kpartx",
                "krb5-libs",
                "less",
                "libacl",
                "libarchive",
                "libassuan",
                "libattr",
                "libbasicobjects",
                "libblkid",
                "libbpf",
                "libbrotli",
                "libcap",
                "libcap-ng",
                "libcbor",
                "libcollection",
                "libcom_err",
                "libcomps",
                "libcurl",
                "libdaemon",
                "libdb",
                "libdhash",
                "libdnf",
                "libeconf",
                "libedit",
                "libevent",
                "libfdisk",
                "libffi",
                "libfido2",
                "libgcc",
                "libgcrypt",
                "libgomp",
                "libgpg-error",
                "libidn2",
                "libini_config",
                "libkcapi",
                "libkcapi-hmaccalc",
                "libksba",
                "libldb",
                "libmnl",
                "libmodulemd",
                "libmount",
                "libndp",
                "libnetfilter_conntrack",
                "libnfnetlink",
                "libnftnl",
                "libnghttp2",
                "libnl3",
                "libnl3-cli",
                "libpath_utils",
                "libpipeline",
                "libpsl",
                "libpwquality",
                "libref_array",
                "librepo",
                "libreport-filesystem",
                "libseccomp",
                "libselinux",
                "libselinux-utils",
                "libsemanage",
                "libsepol",
                "libsigsegv",
                "libsmartcols",
                "libsolv",
                "libss",
                "libssh",
                "libssh-config",
                "libsss_certmap",
                "libsss_idmap",
                "libsss_nss_idmap",
                "libsss_sudo",
                "libstdc++",
                "libsysfs",
                "libtalloc",
                "libtasn1",
                "libtdb",
                "libteam",
                "libtevent",
                "libunistring",
                "libuser",
                "libutempter",
                "libuuid",
                "libverto",
                "libxcrypt",
                "libxml2",
                "libyaml",
                "libzstd",
                "linux-firmware",
                "linux-firmware-whence",
                "lmdb-libs",
                "logrotate",
                "lshw",
                "lsscsi",
                "lua-libs",
                "lz4-libs",
                "lzo",
                "man-db",
                "microcode_ctl",
                "mpfr",
                "ncurses",
                "ncurses-base",
                "ncurses-libs",
                "nettle",
                "NetworkManager",
                "NetworkManager-libnm",
                "NetworkManager-team",
                "NetworkManager-tui",
                "newt",
                "nftables",
                "npth",
                "numactl-libs",
                "oniguruma",
                "openldap",
                "openssh",
                "openssh-clients",
                "openssh-server",
                "openssl",
                "openssl-libs",
                "os-prober",
                "p11-kit",
                "p11-kit-trust",
                "pam",
                "parted",
                "passwd",
                "pciutils-libs",
                "pcre",
                "pcre2",
                "pcre2-syntax",
                "pigz",
                "policycoreutils",
                "popt",
                "prefixdevname",
                "procps-ng",
                "psmisc",
                "publicsuffix-list-dafsa",
                "python3",
                "python3-dateutil",
                "python3-dbus",
                "python3-dnf",
                "python3-dnf-plugins-core",
                "python3-firewall",
                "python3-gobject-base",
                "python3-gobject-base-noarch",
                "python3-gpg",
                "python3-hawkey",
                "python3-libcomps",
                "python3-libdnf",
                "python3-libs",
                "python3-nftables",
                "python3-pip-wheel",
                "python3-rpm",
                "python3-setuptools-wheel",
                "python3-six",
                "python3-systemd",
                "readline",
                "rootfiles",
                "rpm",
                "rpm-build-libs",
                "rpm-libs",
                "rpm-plugin-audit",
                "rpm-plugin-selinux",
                "rpm-sign-libs",
                "sed",
                "selinux-policy",
                "selinux-policy-targeted",
                "setup",
                "sg3_utils",
                "sg3_utils-libs",
                "shadow-utils",
                "slang",
                "snappy",
                "sqlite-libs",
                "squashfs-tools",
                "sssd-client",
                "sssd-common",
                "sssd-kcm",
                "sudo",
                "systemd",
                "systemd-libs",
                "systemd-pam",
                "systemd-rpm-macros",
                "systemd-udev",
                "teamd",
                "tpm2-tss",
                "tzdata",
                "userspace-rcu",
                "util-linux",
                "util-linux-core",
                "vim-minimal",
                "which",
                "xfsprogs",
                "xz",
                "xz-libs",
                "yum",
                "zlib",
            },
            "reponames": {
                "baseos",
            },
        }
    },
    {
        "id": "basic_pkg_group_with_excludes",
        "transactions": [
            {
                "package-specs": [
                    "@core",
                ],
                "exclude-specs": [
                    "dracut-config-rescue",
                    "iwl1000-firmware",
                    "iwl100-firmware",
                    "iwl105-firmware",
                    "iwl135-firmware",
                    "iwl2000-firmware",
                    "iwl2030-firmware",
                    "iwl3160-firmware",
                    "iwl5000-firmware",
                    "iwl5150-firmware",
                    "iwl6000g2a-firmware",
                    "iwl6050-firmware",
                    "iwl7260-firmware",
                ]
            },
        ],
        "results": {
            "packages": {
                "acl",
                "alternatives",
                "attr",
                "audit",
                "audit-libs",
                "authselect",
                "authselect-libs",
                "basesystem",
                "bash",
                "binutils",
                "binutils-gold",
                "bzip2-libs",
                "ca-certificates",
                "c-ares",
                "centos-gpg-keys",
                "centos-stream-release",
                "centos-stream-repos",
                "coreutils",
                "coreutils-common",
                "cpio",
                "cracklib",
                "cracklib-dicts",
                "cronie",
                "cronie-anacron",
                "crontabs",
                "crypto-policies",
                "crypto-policies-scripts",
                "cryptsetup-libs",
                "curl",
                "cyrus-sasl-lib",
                "dbus",
                "dbus-broker",
                "dbus-common",
                "dbus-libs",
                "device-mapper",
                "device-mapper-libs",
                "diffutils",
                "dnf",
                "dnf-data",
                "dnf-plugins-core",
                "dracut",
                "dracut-network",
                "dracut-squash",
                "e2fsprogs",
                "e2fsprogs-libs",
                "elfutils-debuginfod-client",
                "elfutils-default-yama-scope",
                "elfutils-libelf",
                "elfutils-libs",
                "ethtool",
                "expat",
                "file",
                "file-libs",
                "filesystem",
                "findutils",
                "firewalld",
                "firewalld-filesystem",
                "fuse-libs",
                "gawk",
                "gdbm-libs",
                "gettext",
                "gettext-libs",
                "glib2",
                "glibc",
                "glibc-common",
                "glibc-minimal-langpack",
                "gmp",
                "gnupg2",
                "gnutls",
                "gobject-introspection",
                "gpgme",
                "grep",
                "groff-base",
                "grub2-common",
                "grub2-tools",
                "grub2-tools-minimal",
                "grubby",
                "gzip",
                "hostname",
                "hwdata",
                "ima-evm-utils",
                "inih",
                "initscripts-rename-device",
                "initscripts-service",
                "iproute",
                "iproute-tc",
                "ipset",
                "ipset-libs",
                "iptables-libs",
                "iptables-nft",
                "iputils",
                "irqbalance",
                "jansson",
                "jq",
                "json-c",
                "kbd",
                "kbd-legacy",
                "kbd-misc",
                "kernel-tools",
                "kernel-tools-libs",
                "kexec-tools",
                "keyutils",
                "keyutils-libs",
                "kmod",
                "kmod-libs",
                "kpartx",
                "krb5-libs",
                "less",
                "libacl",
                "libarchive",
                "libassuan",
                "libattr",
                "libbasicobjects",
                "libblkid",
                "libbpf",
                "libbrotli",
                "libcap",
                "libcap-ng",
                "libcbor",
                "libcollection",
                "libcom_err",
                "libcomps",
                "libcurl",
                "libdaemon",
                "libdb",
                "libdhash",
                "libdnf",
                "libeconf",
                "libedit",
                "libevent",
                "libfdisk",
                "libffi",
                "libfido2",
                "libgcc",
                "libgcrypt",
                "libgomp",
                "libgpg-error",
                "libidn2",
                "libini_config",
                "libkcapi",
                "libkcapi-hmaccalc",
                "libksba",
                "libldb",
                "libmnl",
                "libmodulemd",
                "libmount",
                "libndp",
                "libnetfilter_conntrack",
                "libnfnetlink",
                "libnftnl",
                "libnghttp2",
                "libnl3",
                "libnl3-cli",
                "libpath_utils",
                "libpipeline",
                "libpsl",
                "libpwquality",
                "libref_array",
                "librepo",
                "libreport-filesystem",
                "libseccomp",
                "libselinux",
                "libselinux-utils",
                "libsemanage",
                "libsepol",
                "libsigsegv",
                "libsmartcols",
                "libsolv",
                "libss",
                "libssh",
                "libssh-config",
                "libsss_certmap",
                "libsss_idmap",
                "libsss_nss_idmap",
                "libsss_sudo",
                "libstdc++",
                "libsysfs",
                "libtalloc",
                "libtasn1",
                "libtdb",
                "libteam",
                "libtevent",
                "libunistring",
                "libuser",
                "libutempter",
                "libuuid",
                "libverto",
                "libxcrypt",
                "libxml2",
                "libyaml",
                "libzstd",
                "linux-firmware",
                "linux-firmware-whence",
                "lmdb-libs",
                "logrotate",
                "lshw",
                "lsscsi",
                "lua-libs",
                "lz4-libs",
                "lzo",
                "man-db",
                "microcode_ctl",
                "mpfr",
                "ncurses",
                "ncurses-base",
                "ncurses-libs",
                "nettle",
                "NetworkManager",
                "NetworkManager-libnm",
                "NetworkManager-team",
                "NetworkManager-tui",
                "newt",
                "nftables",
                "npth",
                "numactl-libs",
                "oniguruma",
                "openldap",
                "openssh",
                "openssh-clients",
                "openssh-server",
                "openssl",
                "openssl-libs",
                "os-prober",
                "p11-kit",
                "p11-kit-trust",
                "pam",
                "parted",
                "passwd",
                "pciutils-libs",
                "pcre",
                "pcre2",
                "pcre2-syntax",
                "pigz",
                "policycoreutils",
                "popt",
                "prefixdevname",
                "procps-ng",
                "psmisc",
                "publicsuffix-list-dafsa",
                "python3",
                "python3-dateutil",
                "python3-dbus",
                "python3-dnf",
                "python3-dnf-plugins-core",
                "python3-firewall",
                "python3-gobject-base",
                "python3-gobject-base-noarch",
                "python3-gpg",
                "python3-hawkey",
                "python3-libcomps",
                "python3-libdnf",
                "python3-libs",
                "python3-nftables",
                "python3-pip-wheel",
                "python3-rpm",
                "python3-setuptools-wheel",
                "python3-six",
                "python3-systemd",
                "readline",
                "rootfiles",
                "rpm",
                "rpm-build-libs",
                "rpm-libs",
                "rpm-plugin-audit",
                "rpm-plugin-selinux",
                "rpm-sign-libs",
                "sed",
                "selinux-policy",
                "selinux-policy-targeted",
                "setup",
                "sg3_utils",
                "sg3_utils-libs",
                "shadow-utils",
                "slang",
                "snappy",
                "sqlite-libs",
                "squashfs-tools",
                "sssd-client",
                "sssd-common",
                "sssd-kcm",
                "sudo",
                "systemd",
                "systemd-libs",
                "systemd-pam",
                "systemd-rpm-macros",
                "systemd-udev",
                "teamd",
                "tpm2-tss",
                "tzdata",
                "userspace-rcu",
                "util-linux",
                "util-linux-core",
                "vim-minimal",
                "which",
                "xfsprogs",
                "xz",
                "xz-libs",
                "yum",
                "zlib",
            },
            "reponames": {
                "baseos",
            },
        }
    },
    # Test that a package can be excluded in one transaction and installed in another
    # This is common scenario for custom packages specified in the Blueprint
    {
        "id": "install_pkg_excluded_in_another_transaction",
        "transactions": [
            {
                "package-specs": [
                    "filesystem",
                ],
                "exclude-specs": [
                    "pkg-with-no-deps",
                ],
            },
            {
                "package-specs": [
                    "pkg-with-no-deps",
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
    # Test that repositories not enabled for the transaction are not used
    # This test should result in an error because the package is not available in the enabled repositories
    {
        "id": "error_pkg_not_in_enabled_repos",
        "transactions": [
            {
                "package-specs": [
                    "filesystem",
                    "pkg-with-no-deps",
                ],
                "repo-ids": [
                    "baseos",
                ]
            },
            {
                "package-specs": [
                    "tmux",
                ],
                "repo-ids": [
                    "baseos",
                    "custom",
                ]
            }
        ],
        "error": True,
        "error_kind": "MarkingErrors",
        "error_reason_re": r".*pkg-with-no-deps.*",
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
    # Test repository error
    {
        "id": "error_unreachable_repo",
        "transactions": [
            {
                "package-specs": [
                    "tmux",
                ],
            },
        ],
        "additional_servers": [
            {
                "name": "broken",
                "address": "file:///non-existing-repo",
            },
        ],
        "error": True,
        "error_kind": "RepoError",
        "error_reason_re": r"There was a problem reading a repository: Failed to download metadata.*['\"]broken['\"].*",
    },
]


dump_test_cases = [
    {
        "id": "basic",
        "packages_count": 4444,
    },
    # Test repository error
    {
        "id": "error_unreachable_repo",
        "additional_servers": [
            {
                "name": "broken",
                "address": "file:///non-existing-repo",
            },
        ],
        "error": True,
        "error_kind": "RepoError",
        "error_reason_re": r"There was a problem reading a repository: Failed to download metadata.*['\"]broken['\"].*",
    },
]


search_test_cases = [
    {
        "id": "1pkg_latest",
        "search_args": {
            "latest": True,
            "packages": [
                "zsh",
            ],
        },
        "results": [
            {
                "name": "zsh",
                "summary": "Powerful interactive shell",
                "description": """The zsh shell is a command interpreter usable as an interactive login
shell and as a shell script command processor.  Zsh resembles the ksh
shell (the Korn shell), but includes many enhancements.  Zsh supports
command line editing, built-in spelling correction, programmable
command completion, shell functions (with autoloading), a history
mechanism, and more.""",
                "url": "http://zsh.sourceforge.net/",
                "repo_id": "baseos",
                "epoch": 0,
                "version": "5.8",
                "release": "9.el9",
                "arch": "x86_64",
                "buildtime": "2022-02-23T13:47:24Z",
                "license": "MIT",
            },
        ],
    },
    {
        "id": "1pkg_not_latest",
        "search_args": {
            "latest": False,
            "packages": [
                "zsh",
            ],
        },
        "results": [
            {
                "name": "zsh",
                "summary": "Powerful interactive shell",
                "description": """The zsh shell is a command interpreter usable as an interactive login
shell and as a shell script command processor.  Zsh resembles the ksh
shell (the Korn shell), but includes many enhancements.  Zsh supports
command line editing, built-in spelling correction, programmable
command completion, shell functions (with autoloading), a history
mechanism, and more.""",
                "url": "http://zsh.sourceforge.net/",
                "repo_id": "baseos",
                "epoch": 0,
                "version": "5.8",
                "release": "7.el9",
                "arch": "x86_64",
                "buildtime": "2021-08-10T06:14:26Z",
                "license": "MIT",
            },
            {
                "name": "zsh",
                "summary": "Powerful interactive shell",
                "description": """The zsh shell is a command interpreter usable as an interactive login
shell and as a shell script command processor.  Zsh resembles the ksh
shell (the Korn shell), but includes many enhancements.  Zsh supports
command line editing, built-in spelling correction, programmable
command completion, shell functions (with autoloading), a history
mechanism, and more.""",
                "url": "http://zsh.sourceforge.net/",
                "repo_id": "baseos",
                "epoch": 0,
                "version": "5.8",
                "release": "9.el9",
                "arch": "x86_64",
                "buildtime": "2022-02-23T13:47:24Z",
                "license": "MIT",
            },
        ],
    },
    # Test repository error
    {
        "id": "error_unreachable_repo",
        "search_args": {
            "latest": True,
            "packages": [
                "curl",
            ]
        },
        "additional_servers": [
            {
                "name": "broken",
                "address": "file:///non-existing-repo",
            },
        ],
        "error": True,
        "error_kind": "RepoError",
        "error_reason_re": r"There was a problem reading a repository: Failed to download metadata.*['\"]broken['\"].*",
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


@pytest.mark.parametrize("test_case", depsolve_test_cases, ids=tcase_idfn)
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

    # pylint: disable=fixme
    # TODO: remove this once dnf5 implementation is fixed
    dnf5_broken_test_cases = [
        "basic_pkg_group_with_excludes",
        "install_pkg_excluded_in_another_transaction",
        "error_pkg_not_in_enabled_repos",
    ]

    if dnf_config == '{"use_dnf5": true}' and test_case["id"] in dnf5_broken_test_cases:
        pytest.skip("This test case is known to be broken with dnf5")

    transactions = test_case["transactions"]

    repo_servers_copy = repo_servers.copy()
    if "additional_servers" in test_case:
        repo_servers_copy.extend(test_case["additional_servers"])

    for repo_configs, root_dir, opt_metadata in config_combos(tmp_path, repo_servers_copy):
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


@pytest.mark.parametrize("test_case", dump_test_cases, ids=tcase_idfn)
@pytest.mark.parametrize("dnf_config, detect_fn", [
    (None, assert_dnf),
    ('{"use_dnf5": false}', assert_dnf),
    ('{"use_dnf5": true}', assert_dnf5),
], ids=["no-config", "dnf4", "dnf5"])
def test_dump(tmp_path, repo_servers, dnf_config, detect_fn, test_case):
    try:
        detect_fn()
    except RuntimeError as e:
        pytest.skip(e)

    repo_servers_copy = repo_servers.copy()
    if "additional_servers" in test_case:
        repo_servers_copy.extend(test_case["additional_servers"])

    for repo_configs, root_dir, opt_metadata in config_combos(tmp_path, repo_servers_copy):
        with TemporaryDirectory() as cache_dir:
            res, exit_code = dump(repo_configs, root_dir, cache_dir, dnf_config, opt_metadata)

            if test_case.get("error", False):
                assert exit_code != 0
                assert res["kind"] == test_case["error_kind"]
                assert re.match(test_case["error_reason_re"], res["reason"], re.DOTALL)
                continue

            assert exit_code == 0
            assert len(res) == test_case["packages_count"]

            for res_pkg in res:
                for key in ["arch", "buildtime", "description", "epoch", "license", "name", "release", "repo_id",
                            "summary", "url", "version"]:
                    assert key in res_pkg
                if res_pkg["name"] == "pkg-with-no-deps":
                    assert res_pkg["repo_id"] == "custom"
                else:
                    assert res_pkg["repo_id"] == "baseos"

            # if opt_metadata includes 'filelists', then each repository 'repodata' must include a file that matches
            # *filelists*
            n_filelist_files = len(glob(f"{cache_dir}/*/repodata/*filelists*"))
            if "filelists" in opt_metadata:
                assert n_filelist_files == len(REPO_PATHS)
            else:
                assert n_filelist_files == 0


@pytest.mark.parametrize("test_case", search_test_cases, ids=tcase_idfn)
@pytest.mark.parametrize("dnf_config, detect_fn", [
    (None, assert_dnf),
    ('{"use_dnf5": false}', assert_dnf),
    ('{"use_dnf5": true}', assert_dnf5),
], ids=["no-config", "dnf4", "dnf5"])
def test_search(tmp_path, repo_servers, dnf_config, detect_fn, test_case):
    try:
        detect_fn()
    except RuntimeError as e:
        pytest.skip(e)

    repo_servers_copy = repo_servers.copy()
    if "additional_servers" in test_case:
        repo_servers_copy.extend(test_case["additional_servers"])

    search_args = test_case["search_args"]

    for repo_configs, root_dir, opt_metadata in config_combos(tmp_path, repo_servers_copy):
        with TemporaryDirectory() as cache_dir:
            res, exit_code = search(search_args, repo_configs, root_dir, cache_dir, dnf_config, opt_metadata)

            if test_case.get("error", False):
                assert exit_code != 0
                assert res["kind"] == test_case["error_kind"]
                assert re.match(test_case["error_reason_re"], res["reason"], re.DOTALL)
                continue

            assert exit_code == 0
            assert res == test_case["results"]

            # if opt_metadata includes 'filelists', then each repository 'repodata' must include a file that matches
            # *filelists*
            n_filelist_files = len(glob(f"{cache_dir}/*/repodata/*filelists*"))
            if "filelists" in opt_metadata:
                assert n_filelist_files == len(REPO_PATHS)
            else:
                assert n_filelist_files == 0
