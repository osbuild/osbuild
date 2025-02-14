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

import jsonschema
import pytest

REPO_PATHS = [
    "./test/data/testrepos/baseos/",
    "./test/data/testrepos/appstream/",
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
    if sp.run(["/usr/bin/python3", "-c", "import dnf"], check=False).returncode != 0:
        raise RuntimeError("Cannot import dnf")


def is_license_expression_available():
    """
    Check if the license-expression package is available.

    The check is not done by importing the package in the current Python environment, because it may be
    running inside a virtual environment where the package is / is not installed. Instead, the check is done by
    running a Python script outside the virtual environment.

    For the same reason, we don't use `sys.executable` to run the script, because it may point to a different
    Python interpreter than the one that will be used when `osbuild-depsolve-dnf` is executed.
    """
    cmd = ["/usr/bin/python3", "-c", "from license_expression import get_spdx_licensing as _"]
    if sp.run(cmd, check=False).returncode != 0:
        return False
    return True


def depsolve(transactions, cache_dir, dnf_config=None, repos=None, root_dir=None,
             opt_metadata=None, with_sbom=False) -> Tuple[dict, int]:
    if not repos and not root_dir:
        raise ValueError("At least one of 'repos' or 'root_dir' must be specified")

    req = {
        "command": "depsolve",
        "arch": ARCH,
        "module_platform_id": f"platform:el{RELEASEVER}",
        "releasever": RELEASEVER,
        "cachedir": cache_dir,
        "arguments": {
            "transactions": transactions,
        }
    }

    if repos:
        req["arguments"]["repos"] = repos

    if root_dir:
        req["arguments"]["root_dir"] = root_dir

    if opt_metadata:
        req["arguments"]["optional-metadata"] = opt_metadata

    if with_sbom:
        req["arguments"]["sbom"] = {"type": "spdx"}

    # If there is a config file, write it to a temporary file and pass it to the depsolver
    with TemporaryDirectory() as cfg_dir:
        env = None
        if dnf_config:
            cfg_file = pathlib.Path(cfg_dir) / "solver.json"
            json.dump(dnf_config, cfg_file.open("w"))
            env = {"OSBUILD_SOLVER_CONFIG": os.fspath(cfg_file)}

        p = sp.run(["./tools/osbuild-depsolve-dnf"], input=json.dumps(req), env=env,
                   check=False, stdout=sp.PIPE, stderr=sys.stderr, universal_newlines=True)

        return json.loads(p.stdout), p.returncode


def dump(cache_dir, dnf_config, repos=None, root_dir=None, opt_metadata=None) -> Tuple[dict, int]:
    if not repos and not root_dir:
        raise ValueError("At least one of 'repos' or 'root_dir' must be specified")

    req = {
        "command": "dump",
        "arch": ARCH,
        "module_platform_id": f"platform:el{RELEASEVER}",
        "releasever": RELEASEVER,
        "cachedir": cache_dir,
        "arguments": {}
    }

    if repos:
        req["arguments"]["repos"] = repos

    if root_dir:
        req["arguments"]["root_dir"] = root_dir

    if opt_metadata:
        req["arguments"]["optional-metadata"] = opt_metadata

    # If there is a config file, write it to a temporary file and pass it to the depsolver
    with TemporaryDirectory() as cfg_dir:
        env = None
        if dnf_config:
            cfg_file = pathlib.Path(cfg_dir) / "solver.json"
            json.dump(dnf_config, cfg_file.open("w"))
            env = {"OSBUILD_SOLVER_CONFIG": os.fspath(cfg_file)}

        p = sp.run(["./tools/osbuild-depsolve-dnf"], input=json.dumps(req), env=env,
                   check=False, stdout=sp.PIPE, stderr=sys.stderr, universal_newlines=True)

        return json.loads(p.stdout), p.returncode


def search(search_args, cache_dir, dnf_config, repos=None, root_dir=None, opt_metadata=None) -> Tuple[dict, int]:
    if not repos and not root_dir:
        raise ValueError("At least one of 'repos' or 'root_dir' must be specified")

    req = {
        "command": "search",
        "arch": ARCH,
        "module_platform_id": f"platform:el{RELEASEVER}",
        "releasever": RELEASEVER,
        "cachedir": cache_dir,
        "arguments": {
            "search": search_args,
        }
    }

    if repos:
        req["arguments"]["repos"] = repos

    if root_dir:
        req["arguments"]["root_dir"] = root_dir

    if opt_metadata:
        req["arguments"]["optional-metadata"] = opt_metadata

    # If there is a config file, write it to a temporary file and pass it to the depsolver
    with TemporaryDirectory() as cfg_dir:
        env = None
        if dnf_config:
            cfg_file = pathlib.Path(cfg_dir) / "solver.json"
            json.dump(dnf_config, cfg_file.open("w"))
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


depsolve_test_case_basic_2pkgs_2repos = {
    "id": "basic_2pkgs_2repos",
    "enabled_repos": ["baseos", "custom"],
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
}


depsolve_test_cases = [
    {
        "id": "basic_1pkg_1repo",
        "enabled_repos": ["baseos", "custom"],
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
        "enabled_repos": ["baseos", "custom"],
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
        "id": "basic_pkg_group",
        "enabled_repos": ["baseos", "custom"],
        "transactions": [
            {
                "package-specs": [
                    "@core",
                ],
            },
        ],
        "results": {
            "packages": {
                "NetworkManager",
                "NetworkManager-libnm",
                "NetworkManager-team",
                "NetworkManager-tui",
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
                "c-ares",
                "ca-certificates",
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
                "iproute",
                "iproute-tc",
                "ipset",
                "ipset-libs",
                "iptables-libs",
                "iptables-nft",
                "iputils",
                "irqbalance",
                "iwl100-firmware",
                "iwl1000-firmware",
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
        "enabled_repos": ["baseos", "custom"],
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
                "NetworkManager",
                "NetworkManager-libnm",
                "NetworkManager-team",
                "NetworkManager-tui",
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
                "c-ares",
                "ca-certificates",
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
        "id": "basic_module",
        "enabled_repos": ["baseos", "appstream", "custom"],
        "transactions": [
            {
                "package-specs": [
                    "@nodejs:18",
                ],
                "exclude-specs": [],
            },
        ],
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
                "libbrotli",
                "libcap",
                "libffi",
                "libgcc",
                "libselinux",
                "libsepol",
                "libsigsegv",
                "libstdc++",
                "libtasn1",
                "ncurses-base",
                "ncurses-libs",
                "nodejs",
                "npm",
                "openssl",
                "openssl-libs",
                "p11-kit",
                "p11-kit-trust",
                "pcre",
                "pcre2",
                "pcre2-syntax",
                "sed",
                "setup",
                "tzdata",
                "zlib",
            },
            "reponames": {
                "appstream",
                "baseos",
            },
            "modules": {"nodejs"},
        }
    },

    # Test that a package can be excluded in one transaction and installed in another
    # This is common scenario for custom packages specified in the Blueprint
    {
        "id": "install_pkg_excluded_in_another_transaction",
        "enabled_repos": ["baseos", "custom"],
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
        "enabled_repos": ["baseos", "custom"],
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
        "enabled_repos": ["baseos", "custom"],
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
        "enabled_repos": ["baseos", "custom"],
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
        "enabled_repos": ["baseos", "custom"],
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
] + [depsolve_test_case_basic_2pkgs_2repos]


dump_test_cases = [
    {
        "id": "basic",
        "enabled_repos": ["baseos", "custom"],
        "packages_count": 4573,
    },
    # Test repository error
    {
        "id": "error_unreachable_repo",
        "enabled_repos": ["baseos", "custom"],
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


search_test_case_basic_2pkgs_2repos = {
    "id": "basic_2pkgs_2repos",
    "enabled_repos": ["baseos", "custom"],
    "search_args": {
        "latest": True,
        "packages": [
            "zsh",
            "pkg-with-no-deps",
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
        {
            'arch': 'noarch',
            'buildtime': '2024-04-15T18:09:19Z',
            'description': 'Provides pkg-with-no-deps',
            'epoch': 0,
            'license': 'BSD',
            'name': 'pkg-with-no-deps',
            'release': '0',
            'repo_id': 'custom',
            'summary': 'Provides pkg-with-no-deps',
            'url': None,
            'version': '1.0.0',
        },
    ],
}


search_test_cases = [
    {
        "id": "1pkg_latest",
        "enabled_repos": ["baseos", "custom"],
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
        "enabled_repos": ["baseos", "custom"],
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
        "enabled_repos": ["baseos", "custom"],
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
] + [search_test_case_basic_2pkgs_2repos]


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


def gen_repo_config(server):
    """
    Generate a repository configuration dictionary for the provided server.
    """
    return {
        "id": server["name"],
        "name": server["name"],
        "baseurl": server["address"],
        "check_gpg": False,
        "sslverify": False,
        "rhsm": False,
        "gpgkeys": [TEST_KEY + server["name"]],
    }


def config_combos(tmp_path, servers):
    """
    Return all configurations for the provided repositories, either as config files in a directory or as repository
    configs in the depsolve request, or a combination of both.
    """
    for combo in gen_config_combos(len(servers)):
        repo_configs = None
        if len(combo[0]):
            repo_configs = []
            for idx in combo[0]:  # servers to be configured through request
                server = servers[idx]
                repo_configs.append(gen_repo_config(server))

        root_dir = None
        if len(combo[1]):
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
            root_dir = os.fspath(root_dir)

        # for each combo, let's also enable or disable filelists (optional-metadata)
        for opt_metadata in ([], ["filelists"]):
            yield repo_configs, root_dir, opt_metadata


def get_test_case_repo_servers(test_case, repo_servers):
    """
    Return a list of repository servers for the test case.
    """
    repo_servers_copy = repo_servers.copy()
    # filter to only include enabled repositories
    repo_servers_copy = [r for r in repo_servers_copy if r["name"] in test_case["enabled_repos"]]
    repo_servers_copy.extend(test_case.get("additional_servers", []))
    return repo_servers_copy


def get_test_case_repo_configs(test_case, repo_servers):
    """
    Return a list of repository configurations for the test case.
    """
    return [gen_repo_config(server) for server in get_test_case_repo_servers(test_case, repo_servers)]


@pytest.mark.parametrize("test_case,repo_servers,expected", [
    (
        {"enabled_repos": ["baseos", "custom"], "additional_servers": []},
        [{"name": "baseos", "address": "file:///baseos"}, {"name": "custom", "address": "file:///custom"}],
        [{"name": "baseos", "address": "file:///baseos"}, {"name": "custom", "address": "file:///custom"}]
    ),
    (
        {"enabled_repos": ["baseos"], "additional_servers": []},
        [{"name": "baseos", "address": "file:///baseos"}, {"name": "custom", "address": "file:///custom"}],
        [{"name": "baseos", "address": "file:///baseos"}]
    ),
    (
        {
            "enabled_repos": ["baseos", "custom"],
            "additional_servers": [{"name": "broken", "address": "file:///broken"}]
        },
        [{"name": "baseos", "address": "file:///baseos"}, {"name": "custom", "address": "file:///custom"}],
        [
            {"name": "baseos", "address": "file:///baseos"},
            {"name": "custom", "address": "file:///custom"},
            {"name": "broken", "address": "file:///broken"},
        ]
    ),
    (
        {
            "enabled_repos": ["baseos"], "additional_servers": [{"name": "broken", "address": "file:///broken"}]
        },
        [{"name": "baseos", "address": "file:///baseos"}, {"name": "custom", "address": "file:///custom"}],
        [
            {"name": "baseos", "address": "file:///baseos"},
            {"name": "broken", "address": "file:///broken"},
        ]
    ),
    (
        {
            "enabled_repos": [],
            "additional_servers": [{"name": "broken", "address": "file:///broken"}]
        },
        [{"name": "baseos", "address": "file:///baseos"}, {"name": "custom", "address": "file:///custom"}],
        [
            {"name": "broken", "address": "file:///broken"},
        ]
    ),
])
def test_get_test_case_repo_servers(test_case, repo_servers, expected):
    assert get_test_case_repo_servers(test_case, repo_servers) == expected


@pytest.mark.parametrize("dnf_config, detect_fn", [
    ({}, assert_dnf),
    ({"use_dnf5": False}, assert_dnf),
    ({"use_dnf5": True}, assert_dnf5),
], ids=["no-config", "dnf4", "dnf5"])
def test_depsolve_config_combos(tmp_path, repo_servers, dnf_config, detect_fn):
    """
    Test all possible configurations of repository configurations for the depsolve function.
    Test on a single test case which installs two packages from two repositories.
    """
    try:
        detect_fn()
    except RuntimeError as e:
        pytest.skip(str(e))

    test_case = depsolve_test_case_basic_2pkgs_2repos
    transactions = test_case["transactions"]
    tc_repo_servers = get_test_case_repo_servers(test_case, repo_servers)

    for repo_configs, root_dir, opt_metadata in config_combos(tmp_path, tc_repo_servers):
        with TemporaryDirectory() as cache_dir:
            res, exit_code = depsolve(
                transactions, cache_dir, dnf_config, repo_configs, root_dir, opt_metadata)

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
                assert n_filelist_files == len(tc_repo_servers)
            else:
                assert n_filelist_files == 0

            use_dnf5 = dnf_config.get("use_dnf5", False)
            if use_dnf5:
                assert res["solver"] == "dnf5"
            else:
                assert res["solver"] == "dnf"


# pylint: disable=too-many-branches
@pytest.mark.parametrize("custom_license_db", [None, "./test/data/spdx/custom-license-index.json"])
@pytest.mark.parametrize("with_sbom", [False, True])
@pytest.mark.parametrize("dnf_config, detect_fn", [
    ({}, assert_dnf),
    ({"use_dnf5": False}, assert_dnf),
    ({"use_dnf5": True}, assert_dnf5),
], ids=["no-config", "dnf4", "dnf5"])
def test_depsolve_sbom(tmp_path, repo_servers, dnf_config, detect_fn, with_sbom, custom_license_db):
    try:
        detect_fn()
    except RuntimeError as e:
        pytest.skip(str(e))

    if custom_license_db:
        if not is_license_expression_available():
            pytest.skip("license_expression python module is not available")

        dnf_config = dnf_config.copy()
        dnf_config["license_index_path"] = custom_license_db

    test_case = depsolve_test_case_basic_2pkgs_2repos
    transactions = test_case["transactions"]
    repo_configs = get_test_case_repo_configs(test_case, repo_servers)

    res, exit_code = depsolve(transactions, tmp_path.as_posix(), dnf_config, repo_configs, with_sbom=with_sbom)

    assert exit_code == 0
    assert {pkg["name"] for pkg in res["packages"]} == test_case["results"]["packages"]
    assert res["repos"].keys() == test_case["results"]["reponames"]

    for repo in res["repos"].values():
        assert repo["gpgkeys"] == [TEST_KEY + repo["id"]]
        assert repo["sslverify"] is False

    if with_sbom:
        assert "sbom" in res

        spdx_2_3_1_schema_file = './test/data/spdx/spdx-schema-v2.3.1.json'
        with open(spdx_2_3_1_schema_file, encoding="utf-8") as f:
            spdx_schema = json.load(f)
        validator = jsonschema.Draft4Validator
        validator.check_schema(spdx_schema)
        spdx_validator = validator(spdx_schema)
        spdx_validator.validate(res["sbom"])

        assert {pkg["name"] for pkg in res["sbom"]["packages"]} == test_case["results"]["packages"]

        license_expressions = [pkg["licenseDeclared"] for pkg in res["sbom"]["packages"]]
        license_refs = [le for le in license_expressions if le.startswith("LicenseRef-")]
        non_license_refs = [le for le in license_expressions if not le.startswith("LicenseRef-")]
        if not is_license_expression_available():
            # all license expressions shhould be converted to ExtractedLicensingInfo
            assert len(license_refs) == len(license_expressions)
            assert len(non_license_refs) == 0
        else:
            # some license expressions should not be converted to ExtractedLicensingInfo
            assert len(license_refs) < len(license_expressions)
            if custom_license_db:
                assert len(non_license_refs) == 5
                # "GPLv2" is not a valid SPDX license expression, but it is added in our custom license db
                assert "GPLv2" in non_license_refs
            else:
                assert len(non_license_refs) == 2
                assert "GPLv2" not in non_license_refs

    else:
        assert "sbom" not in res

    use_dnf5 = dnf_config.get("use_dnf5", False)
    if use_dnf5:
        assert res["solver"] == "dnf5"
    else:
        assert res["solver"] == "dnf"


# pylint: disable=too-many-branches
@pytest.mark.parametrize("test_case", depsolve_test_cases, ids=tcase_idfn)
@pytest.mark.parametrize("dnf_config, detect_fn", [
    ({}, assert_dnf),
    ({"use_dnf5": False}, assert_dnf),
    ({"use_dnf5": True}, assert_dnf5),
], ids=["no-config", "dnf4", "dnf5"])
def test_depsolve(tmp_path, repo_servers, dnf_config, detect_fn, test_case):
    try:
        detect_fn()
    except RuntimeError as e:
        pytest.skip(str(e))

    # pylint: disable=fixme
    # TODO: remove this once dnf5 implementation is fixed
    dnf5_broken_test_cases = [
        "basic_pkg_group_with_excludes",
        "install_pkg_excluded_in_another_transaction",
        "error_pkg_not_in_enabled_repos",
        "basic_module",
    ]

    if dnf_config.get("use_dnf5", False) and test_case["id"] in dnf5_broken_test_cases:
        pytest.skip("This test case is known to be broken with dnf5")

    transactions = test_case["transactions"]
    repo_configs = get_test_case_repo_configs(test_case, repo_servers)

    res, exit_code = depsolve(transactions, tmp_path.as_posix(), dnf_config, repo_configs)

    if test_case.get("error", False):
        assert exit_code != 0
        assert res["kind"] == test_case["error_kind"]
        assert re.match(test_case["error_reason_re"], res["reason"], re.DOTALL)
        return

    assert exit_code == 0
    assert {pkg["name"] for pkg in res["packages"]} == test_case["results"]["packages"]
    assert res["repos"].keys() == test_case["results"]["reponames"]

    # modules is optional here as the dnf5 depsolver never returns any modules
    assert res.get("modules", {}).keys() == test_case["results"].get("modules", set())

    for repo in res["repos"].values():
        assert repo["gpgkeys"] == [TEST_KEY + repo["id"]]
        assert repo["sslverify"] is False

    use_dnf5 = dnf_config.get("use_dnf5", False)
    if use_dnf5:
        assert res["solver"] == "dnf5"
    else:
        assert res["solver"] == "dnf"


@pytest.mark.parametrize("test_case", dump_test_cases, ids=tcase_idfn)
@pytest.mark.parametrize("dnf_config, detect_fn", [
    (None, assert_dnf),
    ({"use_dnf5": False}, assert_dnf),
    ({"use_dnf5": True}, assert_dnf5),
], ids=["no-config", "dnf4", "dnf5"])
def test_dump(tmp_path, repo_servers, dnf_config, detect_fn, test_case):
    try:
        detect_fn()
    except RuntimeError as e:
        pytest.skip(str(e))

    tc_repo_servers = get_test_case_repo_servers(test_case, repo_servers)

    for repo_configs, root_dir, opt_metadata in config_combos(tmp_path, tc_repo_servers):
        with TemporaryDirectory() as cache_dir:
            res, exit_code = dump(cache_dir, dnf_config, repo_configs, root_dir, opt_metadata)

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
                assert n_filelist_files == len(tc_repo_servers)
            else:
                assert n_filelist_files == 0


@pytest.mark.parametrize("dnf_config, detect_fn", [
    (None, assert_dnf),
    ({"use_dnf5": False}, assert_dnf),
    ({"use_dnf5": True}, assert_dnf5),
], ids=["no-config", "dnf4", "dnf5"])
def test_search_config_combos(tmp_path, repo_servers, dnf_config, detect_fn):
    """
    Test all possible configurations of repository configurations for the search function.
    Test on a single test case which searches for two packages from two repositories.
    """
    try:
        detect_fn()
    except RuntimeError as e:
        pytest.skip(str(e))

    test_case = search_test_case_basic_2pkgs_2repos
    tc_repo_servers = get_test_case_repo_servers(test_case, repo_servers)
    search_args = test_case["search_args"]

    for repo_configs, root_dir, opt_metadata in config_combos(tmp_path, tc_repo_servers):
        with TemporaryDirectory() as cache_dir:
            res, exit_code = search(search_args, cache_dir, dnf_config, repo_configs, root_dir, opt_metadata)

            assert exit_code == 0
            for res, exp in zip(res, test_case["results"]):
                # if the url in the package is empty, DNF4 returns None, DNF5 returns an empty string
                exp = exp.copy()
                exp_url = exp.pop("url")
                res_url = res.pop("url")
                if exp_url is None and dnf_config and dnf_config.get("use_dnf5", False):
                    assert res_url == ""
                else:
                    assert res_url == exp_url
                assert res == exp

            # if opt_metadata includes 'filelists', then each repository 'repodata' must include a file that matches
            # *filelists*
            n_filelist_files = len(glob(f"{cache_dir}/*/repodata/*filelists*"))
            if "filelists" in opt_metadata:
                assert n_filelist_files == len(tc_repo_servers)
            else:
                assert n_filelist_files == 0


@pytest.mark.parametrize("test_case", search_test_cases, ids=tcase_idfn)
@pytest.mark.parametrize("dnf_config, detect_fn", [
    (None, assert_dnf),
    ({"use_dnf5": False}, assert_dnf),
    ({"use_dnf5": True}, assert_dnf5),
], ids=["no-config", "dnf4", "dnf5"])
def test_search(tmp_path, repo_servers, dnf_config, detect_fn, test_case):
    try:
        detect_fn()
    except RuntimeError as e:
        pytest.skip(str(e))

    repo_configs = get_test_case_repo_configs(test_case, repo_servers)
    search_args = test_case["search_args"]

    res, exit_code = search(search_args, tmp_path.as_posix(), dnf_config, repo_configs)

    if test_case.get("error", False):
        assert exit_code != 0
        assert res["kind"] == test_case["error_kind"]
        assert re.match(test_case["error_reason_re"], res["reason"], re.DOTALL)
        return

    assert exit_code == 0
    for res, exp in zip(res, test_case["results"]):
        # if the url in the package is empty, DNF4 returns None, DNF5 returns an empty string
        exp = exp.copy()
        exp_url = exp.pop("url")
        res_url = res.pop("url")
        if exp_url is None and dnf_config and dnf_config.get("use_dnf5", False):
            assert res_url == ""
        else:
            assert res_url == exp_url
        assert res == exp


def test_depsolve_result_api(tmp_path, repo_servers):
    """
    Test the result of depsolve() API.

    Note tha this test runs only with dnf4, as the dnf5 depsolver does not support modules.
    """
    try:
        assert_dnf()
    except RuntimeError as e:
        pytest.skip(str(e))

    cache_dir = (tmp_path / "depsolve-cache").as_posix()
    transactions = [
        {
            # we pick this package to get a "modules" result
            "package-specs": ["@nodejs:18"],
        },
    ]

    repo_configs = [gen_repo_config(server) for server in repo_servers]
    res, exit_code = depsolve(transactions, cache_dir, repos=repo_configs)

    assert exit_code == 0
    # If any of  this changes, increase:
    #   "Provides: osbuild-dnf-json-api" inosbuild.spec
    assert list(res.keys()) == ["solver", "packages", "repos", "modules"]
    assert isinstance(res["solver"], str)
    assert sorted(res["packages"][0].keys()) == [
        "arch",
        "checksum",
        "epoch",
        "name",
        "path",
        "release",
        "remote_location",
        "repo_id",
        "version",
    ]
    assert sorted(res["repos"]["baseos"].keys()) == [
        "baseurl",
        "gpgcheck",
        "gpgkeys",
        "id",
        "metalink",
        "mirrorlist",
        "name",
        "repo_gpgcheck",
        "sslcacert",
        "sslclientcert",
        "sslclientkey",
        "sslverify",
    ]
    assert sorted(res["modules"]["nodejs"]["module-file"].keys()) == [
        "data",
        "path",
    ]
    assert sorted(res["modules"]["nodejs"]["module-file"]["data"].keys()) == [
        "name",
        "profiles",
        "state",
        "stream",
    ]
    assert list(res["modules"]["nodejs"]["failsafe-file"].keys()) == [
        "data",
        "path",
    ]
