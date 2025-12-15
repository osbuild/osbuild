# pylint: disable=too-many-lines

import configparser
import json
import os
import pathlib
import re
import subprocess as sp
import sys
from glob import glob
from itertools import combinations
from tempfile import TemporaryDirectory
from typing import Tuple

import jsonschema
import pytest

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

    The check is not done by importing the package in the current Python environment, because "osbuild-depsolve-dnf"
    is run outside of any virtualenv that that the tests may run in. It is inside "osbuild-depsolve-dnf" where
    the import for "license_expression" happens. Therefore the check is done by running an external Python script
    outside the potential virtualenv.

    For the same reason, we don't use `sys.executable` to run the script, because it may point to a different
    Python interpreter than the one that will be used when `osbuild-depsolve-dnf` is executed.
    """
    cmd = ["/usr/bin/python3", "-c", "from license_expression import get_spdx_licensing as _"]
    if sp.run(cmd, check=False).returncode != 0:
        return False
    return True


def _run_solver(request: dict, dnf_config: dict = None) -> Tuple[dict, int]:
    """
    Execute the solver with the given request and return (response, exit_code).

    If dnf_config is provided, it will be written to a temporary file and passed
    to the solver via the OSBUILD_SOLVER_CONFIG environment variable.
    """
    with TemporaryDirectory() as cfg_dir:
        env = None
        if dnf_config:
            cfg_file = pathlib.Path(cfg_dir) / "solver.json"
            json.dump(dnf_config, cfg_file.open("w"))
            env = {"OSBUILD_SOLVER_CONFIG": os.fspath(cfg_file)}

        p = sp.run(["./tools/osbuild-depsolve-dnf"], input=json.dumps(request), env=env,
                   check=False, stdout=sp.PIPE, stderr=sys.stderr, universal_newlines=True)

        return json.loads(p.stdout), p.returncode


def depsolve(transactions, cache_dir, dnf_config=None, repos=None, root_dir=None,
             opt_metadata=None, with_sbom=False) -> Tuple[dict, int]:
    if not repos and not root_dir:
        raise ValueError("At least one of 'repos' or 'root_dir' must be specified")

    req = {
        "command": "depsolve",
        "arch": ARCH,
        "releasever": RELEASEVER,
        "cachedir": cache_dir,
        "arguments": {
            "transactions": transactions,
        }
        # Note that we are not setting "module_platform_id" here,
        # none of our tests is using it. Once we start using it
        # we need to add it (and maybe a "with_platform_id" as
        # parameter on top)
    }

    if repos:
        req["arguments"]["repos"] = repos

    if root_dir:
        req["arguments"]["root_dir"] = root_dir

    if opt_metadata:
        req["arguments"]["optional-metadata"] = opt_metadata

    if with_sbom:
        req["arguments"]["sbom"] = {"type": "spdx"}

    return _run_solver(req, dnf_config)


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

    return _run_solver(req, dnf_config)


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

    return _run_solver(req, dnf_config)


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
    # Test no repositories
    {
        "id": "error_empty_rootdir_no_repos",
        "enabled_repos": [],
        "root_dir": "/dev/null",
        "transactions": [
            {
                "package-specs": [
                    "filesystem",
                ],
            },
        ],
        "error": True,
        "error_kind": "NoReposError",
        "error_reason_re": r".*There are no enabled repositories",
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
    "expected_nevras": [
        "zsh-0:5.8-9.el9.x86_64",
        "pkg-with-no-deps-0:1.0.0-0.noarch",
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
        "expected_nevras": [
            "zsh-0:5.8-9.el9.x86_64",
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
        "expected_nevras": [
            "zsh-0:5.8-7.el9.x86_64",
            "zsh-0:5.8-9.el9.x86_64",
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
        "baseurl": [server["address"]],
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


def assert_depsolve_api_v1_response(res, expected_pkgs, expected_repos, expected_modules, with_dnf5, with_sbom):
    """
    Helper function to check the v1 API response of depsolve().

    If any of the fields in the response changes, increase:
        "Provides: osbuild-dnf-json-api" in osbuild.spec
    """

    tl_keys = ["solver", "packages", "repos", "modules"]
    if with_sbom:
        tl_keys.append("sbom")
    assert list(res.keys()) == tl_keys

    assert res["solver"] == "dnf5" if with_dnf5 else "dnf"
    assert {pkg["name"] for pkg in res["packages"]} == expected_pkgs
    for pkg in res["packages"]:
        assert sorted(pkg.keys()) == [
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
    assert res["repos"].keys() == expected_repos
    for repo in res["repos"].values():
        assert sorted(repo.keys()) == [
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
        assert repo["gpgkeys"] == [TEST_KEY + repo["id"]]
        assert repo["sslverify"] is False

    if with_sbom:
        assert "sbom" in res
        assert isinstance(res["sbom"], dict)
        assert res["sbom"] != {}

    assert len(res["modules"]) == len(expected_modules)
    for module_name in expected_modules:
        assert sorted(res["modules"][module_name]["module-file"].keys()) == [
            "data",
            "path",
        ]
        assert sorted(res["modules"][module_name]["module-file"]["data"].keys()) == [
            "name",
            "profiles",
            "state",
            "stream",
        ]
        assert sorted(res["modules"][module_name]["failsafe-file"].keys()) == [
            "data",
            "path",
        ]


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

            # if opt_metadata includes 'filelists', then each repository 'repodata' must include a file that matches
            # *filelists*
            n_filelist_files = len(glob(f"{cache_dir}/*/repodata/*filelists*"))
            if "filelists" in opt_metadata:
                assert n_filelist_files == len(tc_repo_servers)
            else:
                assert n_filelist_files == 0

            assert_depsolve_api_v1_response(
                res,
                expected_pkgs=test_case["results"]["packages"],
                expected_repos=test_case["results"]["reponames"],
                expected_modules=test_case["results"].get("modules", set()),
                with_dnf5=dnf_config.get("use_dnf5", False),
                with_sbom=False
            )


def set_config_dnfvars(baseurl, dnfvars):
    for j, url in enumerate(baseurl):
        for var, value in dnfvars.items():
            if value in url:
                baseurl[j] = url.replace(value, f"${var}")
    return baseurl


def create_dnfvars(root_dir, dnfvars):
    vars_dir = root_dir / "etc/dnf/vars"
    vars_dir.mkdir(parents=True)

    for var, value in dnfvars.items():
        var_path = vars_dir / var
        var_path.write_text(value, encoding="utf8")


@pytest.mark.parametrize("use_dnfvars", [True, False], ids=["with_dnfvars", "without_dnfvars"])
@pytest.mark.parametrize("dnf_config, detect_fn", [
    ({}, assert_dnf),
    ({"use_dnf5": False}, assert_dnf),
    ({"use_dnf5": True}, assert_dnf5),
], ids=["no-config", "dnf4", "dnf5"])
def test_depsolve_dnfvars(tmp_path, repo_servers, dnf_config, detect_fn, use_dnfvars):
    try:
        detect_fn()
    except RuntimeError as e:
        pytest.skip(str(e))

    test_case = depsolve_test_case_basic_2pkgs_2repos
    transactions = test_case["transactions"]
    repo_configs = get_test_case_repo_configs(test_case, repo_servers)
    root_dir = None

    for index, config in enumerate(repo_configs):
        repo_configs[index]["baseurl"] = set_config_dnfvars(config["baseurl"], {"var": "localhost"})

    if use_dnfvars:
        create_dnfvars(tmp_path, {"var": "localhost"})
        root_dir = str(tmp_path)

    res, exit_code = depsolve(transactions, tmp_path.as_posix(), dnf_config, repo_configs, root_dir=root_dir)

    if not use_dnfvars:
        assert exit_code != 0
        assert res["kind"] == "RepoError"
        assert re.match(
            "There was a problem reading a repository: Failed to download metadata", res["reason"], re.DOTALL)
        return

    assert exit_code == 0

    assert_depsolve_api_v1_response(
        res,
        expected_pkgs=test_case["results"]["packages"],
        expected_repos=test_case["results"]["reponames"],
        expected_modules=test_case["results"].get("modules", set()),
        with_dnf5=dnf_config.get("use_dnf5", False),
        with_sbom=False
    )


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

    assert_depsolve_api_v1_response(
        res,
        expected_pkgs=test_case["results"]["packages"],
        expected_repos=test_case["results"]["reponames"],
        expected_modules=test_case["results"].get("modules", set()),
        with_dnf5=dnf_config.get("use_dnf5", False),
        with_sbom=with_sbom
    )

    if with_sbom:
        sbom_dict = res["sbom"]
        spdx_2_3_1_schema_file = './test/data/spdx/spdx-schema-v2.3.1.json'
        with open(spdx_2_3_1_schema_file, encoding="utf-8") as f:
            spdx_schema = json.load(f)
        validator = jsonschema.Draft4Validator
        validator.check_schema(spdx_schema)
        spdx_validator = validator(spdx_schema)
        spdx_validator.validate(sbom_dict)

        assert {pkg["name"] for pkg in sbom_dict["packages"]} == test_case["results"]["packages"]

        license_expressions = [pkg["licenseDeclared"] for pkg in sbom_dict["packages"]]
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

    with_dnf5 = dnf_config.get("use_dnf5", False)
    if with_dnf5 and test_case["id"] in dnf5_broken_test_cases:
        pytest.skip("This test case is known to be broken with dnf5")

    transactions = test_case["transactions"]
    repo_configs = get_test_case_repo_configs(test_case, repo_servers)
    root_dir = test_case.get("root_dir")

    res, exit_code = depsolve(transactions, tmp_path.as_posix(), dnf_config, repo_configs, root_dir=root_dir)

    if test_case.get("error", False):
        assert exit_code != 0
        assert res["kind"] == test_case["error_kind"]
        assert re.match(test_case["error_reason_re"], res["reason"], re.DOTALL)
        return

    assert exit_code == 0

    assert_depsolve_api_v1_response(
        res,
        expected_pkgs=test_case["results"]["packages"],
        expected_repos=test_case["results"]["reponames"],
        expected_modules=test_case["results"].get("modules", set()),
        with_dnf5=with_dnf5,
        with_sbom=False
    )


def assert_dump_api_v1_response(res, expected_pkgs_count, pkg_check_fn=None):
    """
    Helper function to check the v1 API response of dump() and search().
    """
    assert len(res) == expected_pkgs_count
    for pkg in res:
        assert sorted(pkg.keys()) == [
            "arch",
            "buildtime",
            "description",
            "epoch",
            "license",
            "name",
            "release",
            "repo_id",
            "summary",
            "url",
            "version",
        ]
        if pkg_check_fn:
            pkg_check_fn(pkg)


def assert_search_api_v1_response(res, expected_nevras):
    """
    Helper function to check the v1 API response of search().
    """
    assert len(res) == len(expected_nevras)
    nevras = []
    for pkg in res:
        assert sorted(pkg.keys()) == [
            "arch",
            "buildtime",
            "description",
            "epoch",
            "license",
            "name",
            "release",
            "repo_id",
            "summary",
            "url",
            "version",
        ]
        nevras.append(f"{pkg['name']}-{pkg['epoch']}:{pkg['version']}-{pkg['release']}.{pkg['arch']}")
    assert sorted(nevras) == sorted(expected_nevras)


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

            def pkg_check_fn(pkg):
                if pkg["name"] == "pkg-with-no-deps":
                    assert pkg["repo_id"] == "custom"
                else:
                    assert pkg["repo_id"] == "baseos"

            assert_dump_api_v1_response(res, test_case["packages_count"], pkg_check_fn)

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
            assert_search_api_v1_response(res, test_case["expected_nevras"])

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
    assert_search_api_v1_response(res, test_case["expected_nevras"])


# Test invalid requests for the V1 API
invalid_request_v1_test_cases = [
    # Missing required fields
    {
        "id": "missing_command",
        "request": {
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {"repos": []},
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Missing required field 'command'",
    },
    {
        "id": "missing_arch",
        "request": {
            "command": "depsolve",
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {"repos": []},
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Missing required field 'arch'",
    },
    {
        "id": "missing_releasever",
        "request": {
            "command": "depsolve",
            "arch": ARCH,
            "cachedir": "/tmp/cache",
            "arguments": {"repos": []},
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Missing required field 'releasever'",
    },
    {
        "id": "missing_cachedir",
        "request": {
            "command": "depsolve",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "arguments": {"repos": []},
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Missing required field 'cachedir'",
    },
    {
        "id": "missing_arguments",
        "request": {
            "command": "depsolve",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Missing required field 'arguments'",
    },
    # Invalid command
    {
        "id": "invalid_command",
        "request": {
            "command": "invalid_command",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {"repos": []},
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Invalid command 'invalid_command': must be one of depsolve, dump, search",
    },
    # Invalid field types
    {
        "id": "arguments_not_dict",
        "request": {
            "command": "depsolve",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": "not a dict",
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Field 'arguments' must be a dict",
    },
    {
        "id": "repos_not_list",
        "request": {
            "command": "depsolve",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": "not a list",
            },
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Field 'repos' must be a list",
    },
    {
        "id": "transactions_not_list",
        "request": {
            "command": "depsolve",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [
                    {"id": "custom", "baseurl": [f"file://{os.path.abspath('./test/data/testrepos/custom/')}/"]}
                ],
                "transactions": "not a list",
            },
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Field 'transactions' must be a list",
    },
    {
        "id": "optional_metadata_not_list",
        "request": {
            "command": "depsolve",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [
                    {"id": "custom", "baseurl": [f"file://{os.path.abspath('./test/data/testrepos/custom/')}/"]}
                ],
                "optional-metadata": "not a list",
            },
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Field 'optional-metadata' must be a list",
    },
    {
        "id": "search_not_dict",
        "request": {
            "command": "search",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [
                    {"id": "custom", "baseurl": [f"file://{os.path.abspath('./test/data/testrepos/custom/')}/"]}
                ],
                "search": "not a dict",
            },
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Field 'search' must be a dict",
    },
    # SBOM validation
    {
        "id": "sbom_not_dict",
        "request": {
            "command": "depsolve",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [],
                "sbom": "not a dict",
            },
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Field 'sbom' must be a dict",
    },
    {
        "id": "sbom_missing_type",
        "request": {
            "command": "depsolve",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [],
                "sbom": {},
            },
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Missing required field 'type' in 'sbom'",
    },
    {
        "id": "sbom_with_dump_command",
        "request": {
            "command": "dump",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [],
                "sbom": {"type": "spdx"},
            },
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Field 'sbom' is only supported with 'depsolve' command",
    },
    {
        "id": "sbom_with_search_command",
        "request": {
            "command": "search",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [],
                "search": {"packages": ["package"]},
                "sbom": {"type": "spdx"},
            },
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Field 'sbom' is only supported with 'depsolve' command",
    },
    # Invalid repository config
    {
        "id": "repo_not_dict",
        "request": {
            "command": "depsolve",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": ["not a dict"],
            },
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Repository config must be a dict",
    },
    {
        "id": "repo_missing_id",
        "request": {
            "command": "depsolve",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"name": "test"}],
            },
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Missing required field 'id' in 'repos' item configuration",
    },
    {
        "id": "repo_no_baseurl_metalink_mirrorlist",
        "request": {
            "command": "depsolve",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "test"}],
            },
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"At least one of 'baseurl', 'metalink', or 'mirrorlist' must be specified",
    },
    # Invalid transaction config
    {
        "id": "transaction_not_dict",
        "request": {
            "command": "depsolve",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [
                    {"id": "custom", "baseurl": [f"file://{os.path.abspath('./test/data/testrepos/custom/')}/"]}
                ],
                "transactions": ["not a dict"],
            },
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Invalid depsolve transaction: Depsolve transaction must be a dict",
    },
    # Invalid search arguments
    {
        "id": "search_missing_packages",
        "request": {
            "command": "search",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [
                    {"id": "custom", "baseurl": [f"file://{os.path.abspath('./test/data/testrepos/custom/')}/"]}
                ],
                "search": {"latest": True},
            },
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Missing required field 'packages' in 'search' dict",
    },
    {
        "id": "search_packages_not_list",
        "request": {
            "command": "search",
            "arch": ARCH,
            "releasever": RELEASEVER,
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [
                    {"id": "custom", "baseurl": [f"file://{os.path.abspath('./test/data/testrepos/custom/')}/"]}
                ],
                "search": {"packages": 1},
            },
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Field 'packages' must be a list",
    },
]


invalid_request_common_test_cases = [
    # invalid api_version field
    {
        "id": "with_api_version_999",
        "request": {
            "api_version": 999,
        },
        "error_kind": "InvalidRequest",
        "error_reason_re": r"Invalid API version: 999 is not a valid SolverAPIVersion",
    },
]


@pytest.mark.parametrize(
    "api_version,test_case",
    [("v1", tc) for tc in invalid_request_v1_test_cases] +
    [("common", tc) for tc in invalid_request_common_test_cases],
    ids=lambda x: x if isinstance(x, str) else tcase_idfn(x)
)
@pytest.mark.parametrize("dnf_config, detect_fn", [
    (None, assert_dnf),
    ({"use_dnf5": False}, assert_dnf),
    ({"use_dnf5": True}, assert_dnf5),
], ids=["no-config", "dnf4", "dnf5"])
def test_invalid_requests(tmp_path, api_version, test_case, dnf_config, detect_fn):
    """
    Test that invalid requests are properly rejected with appropriate error messages.
    """
    _ = api_version
    try:
        detect_fn()
    except RuntimeError as e:
        pytest.skip(str(e))

    request = test_case["request"].copy()
    if request.get("cachedir") == "/tmp/cache":
        request["cachedir"] = tmp_path.as_posix()

    result, exit_code = _run_solver(request, dnf_config)

    assert exit_code != 0
    assert result["kind"] == test_case["error_kind"]
    assert re.search(test_case["error_reason_re"], result["reason"], re.DOTALL)
