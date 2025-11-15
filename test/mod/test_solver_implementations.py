"""
Test the DNF solver implementations (DNF4 and DNF5).
"""

import os.path
import re

import pytest

from osbuild.solver.model import Checksum, Dependency, Package, Repository

from .conftest import assert_object_equal

# NB: for sanity testing specific packages, we need to use a local repository, to ensure stable 'remote_locations'
# otherwise, the port number in the server URL would change between tests, causing the test to fail.
TEST_REPO_SERVERS = [
    {
        "name": "baseos",
        "address": f"file://{os.path.abspath('./test/data/testrepos/baseos/')}",
    },
    {
        "name": "appstream",
        "address": f"file://{os.path.abspath('./test/data/testrepos/appstream/')}",
    },
    {
        "name": "custom",
        "address": f"file://{os.path.abspath('./test/data/testrepos/custom/')}",
    }
]

BASH_PACKAGE = Package(
    name="bash",
    version="5.1.8",
    release="9.el9",
    arch="x86_64",
    epoch=0,
    group="Unspecified",
    download_size=1765294,
    install_size=7738778,
    license="GPLv3+",
    source_rpm="bash-5.1.8-9.el9.src.rpm",
    build_time=1708011409,
    packager="builder@centos.org",
    vendor="CentOS",
    url="https://www.gnu.org/software/bash",
    summary="The GNU Bourne Again shell",
    description="The GNU Bourne Again shell (Bash) is a shell or command language\ninterpreter that is compatible with the Bourne shell (sh). Bash\nincorporates useful features from the Korn shell (ksh) and the C shell\n(csh). Most sh scripts can be run by bash without modification.",
    provides=[
        Dependency(name="/bin/bash"),
        Dependency(name="/bin/sh"),
        Dependency(name="bash", relation="=", version="5.1.8-9.el9"),
        Dependency(name="bash(x86-64)", relation="=", version="5.1.8-9.el9"),
        Dependency(name="config(bash)", relation="=", version="5.1.8-9.el9"),
    ],
    requires=[
        Dependency(name="filesystem", relation=">=", version="3"),
        Dependency(name="libc.so.6(GLIBC_2.34)(64bit)"),
        Dependency(name="libtinfo.so.6()(64bit)"),
        Dependency(name="rtld(GNU_HASH)"),
    ],
    regular_requires=[
        Dependency(name="filesystem", relation=">=", version="3"),
        Dependency(name="libc.so.6(GLIBC_2.34)(64bit)"),
        Dependency(name="libtinfo.so.6()(64bit)"),
        Dependency(name="rtld(GNU_HASH)"),
    ],
    files=[
        "/etc/skel/.bash_logout",
        "/etc/skel/.bash_profile",
        "/etc/skel/.bashrc",
        "/usr/bin/alias",
        "/usr/bin/bash",
        "/usr/bin/bashbug",
        "/usr/bin/bashbug-64",
        "/usr/bin/bg",
        "/usr/bin/cd",
        "/usr/bin/command",
        "/usr/bin/fc",
        "/usr/bin/fg",
        "/usr/bin/getopts",
        "/usr/bin/hash",
        "/usr/bin/jobs",
        "/usr/bin/read",
        "/usr/bin/sh",
        "/usr/bin/type",
        "/usr/bin/ulimit",
        "/usr/bin/umask",
        "/usr/bin/unalias",
        "/usr/bin/wait",
    ],
    location="Packages/bash-5.1.8-9.el9.x86_64.rpm",
    remote_locations=[f"{TEST_REPO_SERVERS[0]['address']}/Packages/bash-5.1.8-9.el9.x86_64.rpm"],
    checksum=Checksum(algorithm="sha256", value="823859a9e8fad83004fa0d9f698ff223f6f7d38fd8e7629509d98b5ba6764c03"),
    header_checksum=None,
    repo_id="baseos",
    reason="",
)

PKG_WITH_NO_DEPS_PACKAGE = Package(
    name="pkg-with-no-deps",
    version="1.0.0",
    release="0",
    arch="noarch",
    epoch=0,
    group="Unspecified",
    download_size=6137,
    install_size=0,
    license="BSD",
    source_rpm="pkg-with-no-deps-1.0.0-0.src.rpm",
    build_time=1713204559,
    packager="",
    vendor="noone",
    url="",
    summary="Provides pkg-with-no-deps",
    description="Provides pkg-with-no-deps",
    provides=[
        Dependency(name="pkg-with-no-deps"),
        Dependency(name="pkg-with-no-deps", relation="=", version="1.0.0-0"),
    ],
    location="pkg-with-no-deps-1.0.0-0.noarch.rpm",
    remote_locations=[f"{TEST_REPO_SERVERS[2]['address']}/pkg-with-no-deps-1.0.0-0.noarch.rpm"],
    checksum=Checksum(algorithm="sha256", value="ef05a91ed8bf760cb4d31024c9b5345eda6c1cfd93a01b63b04d4bfa4839bc1c"),
    repo_id="custom",
    reason="",
)

TEST_PACKAGES = {
    "bash": BASH_PACKAGE,
    "pkg-with-no-deps": PKG_WITH_NO_DEPS_PACKAGE,
}

TEST_REPOSITORY = Repository(
    repo_id="baseos",
    name="baseos",
    baseurl=[TEST_REPO_SERVERS[0]["address"]],
    gpgcheck=False,
    repo_gpgcheck=False,
    sslverify=True,
    sslcacert="",
    sslclientkey="",
    sslclientcert="",
)


def assert_rpm_package_valid_basic(rpm_pkg):
    """
    Do basic checks for an RPM Package object.
    """
    # check that the package has the attributes that are expected to be non-empty
    non_empty_string_attrs = [
        "name",
        "version",
        "release",
        "arch",
        "group",
        "license",
        "source_rpm",
        "vendor",
        "summary",
        "description",
        "location",
        "repo_id",
    ]
    for attr in non_empty_string_attrs:
        attr_value = getattr(rpm_pkg, attr)
        assert isinstance(attr_value, str), f"Attribute {attr} for {rpm_pkg.name} is not a string"
        assert attr_value != "", f"Attribute {attr} for {rpm_pkg.name} is empty"

    assert isinstance(rpm_pkg.epoch, int)
    assert rpm_pkg.epoch >= 0

    # check that the package has the optional attributes
    string_attrs_if_set = [
        "packager",
        "url",
    ]
    for attr in string_attrs_if_set:
        attr_value = getattr(rpm_pkg, attr)
        if attr_value is not None:
            assert isinstance(attr_value, str), f"Attribute {attr} for {rpm_pkg.name} is not a string"

    non_zero_int_attrs = [
        "download_size",
        "build_time",
    ]
    for attr in non_zero_int_attrs:
        attr_value = getattr(rpm_pkg, attr)
        assert isinstance(attr_value, int)
        assert attr_value > 0

    # NB: some packages have an install size of 0, because they are virtual packages
    assert isinstance(rpm_pkg.install_size, int)
    assert rpm_pkg.install_size >= 0

    non_empty_list_attrs = [
        "provides",  # every package must have at least one provides
        "remote_locations",
    ]
    for attr in non_empty_list_attrs:
        attr_value = getattr(rpm_pkg, attr)
        assert isinstance(attr_value, list)
        assert len(attr_value) > 0

    list_attrs = [
        "requires",
        "requires_pre",
        "conflicts",
        "obsoletes",
        "regular_requires",
        "recommends",
        "suggests",
        "enhances",
        "supplements",
        "files",
    ]
    for attr in list_attrs:
        attr_value = getattr(rpm_pkg, attr)
        assert isinstance(attr_value, list)
        assert len(attr_value) >= 0

    # every package must have a checksum
    assert rpm_pkg.checksum is not None
    # NB: the packages in our test repository are all SHA256
    assert rpm_pkg.checksum.algorithm == "sha256"
    assert re.match(r'^[0-9a-fA-F]{64}$', rpm_pkg.checksum.value)

    if rpm_pkg.header_checksum is not None:
        assert isinstance(rpm_pkg.header_checksum.algorithm, str)
        assert rpm_pkg.header_checksum.algorithm != ""
        assert isinstance(rpm_pkg.header_checksum.value, str)
        assert re.match(r'^[0-9a-fA-F]+$', rpm_pkg.header_checksum.value)


def test_dnf4_pkg_to_package():
    """Test DNF4's conversion of DNF packages to model.Package objects."""
    testutil_dnf4 = pytest.importorskip("osbuild.testutil.dnf4")
    dnf4_solver = pytest.importorskip("osbuild.solver.dnf")

    dnf_pkgset = testutil_dnf4.depsolve_pkgset(TEST_REPO_SERVERS, ["bash", "pkg-with-no-deps"])

    checked_packages = set()
    for dnf_pkg in dnf_pkgset:
        # pylint: disable=protected-access
        rpm_pkg = dnf4_solver._dnf_pkg_to_package(dnf_pkg)
        assert_rpm_package_valid_basic(rpm_pkg)

        test_package = TEST_PACKAGES.get(dnf_pkg.name)
        if test_package is not None:
            checked_packages.add(dnf_pkg.name)
            assert_object_equal(rpm_pkg, test_package)

    unchecked_test_packages = set(TEST_PACKAGES.keys()) - checked_packages
    assert len(unchecked_test_packages) == 0, f"Following test packages were not checked: {unchecked_test_packages}"


def test_dnf5_pkg_to_package():
    """Test DNF5's conversion of DNF packages to model.Package objects."""
    testutil_dnf5 = pytest.importorskip("osbuild.testutil.dnf5")
    dnf5_solver = pytest.importorskip("osbuild.solver.dnf5")

    _, dnf_pkgset = testutil_dnf5.depsolve_pkgset(TEST_REPO_SERVERS, ["bash", "pkg-with-no-deps"])

    checked_packages = set()
    for dnf_pkg in dnf_pkgset:
        # pylint: disable=protected-access
        rpm_pkg = dnf5_solver._dnf_pkg_to_package(dnf_pkg)
        assert_rpm_package_valid_basic(rpm_pkg)

        test_package = TEST_PACKAGES.get(dnf_pkg.get_name())
        if test_package is not None:
            checked_packages.add(dnf_pkg.get_name())
            assert_object_equal(rpm_pkg, test_package)

    unchecked_test_packages = set(TEST_PACKAGES.keys()) - checked_packages
    assert len(unchecked_test_packages) == 0, f"Following test packages were not checked: {unchecked_test_packages}"


def test_dnf4_dnf5_package_parity(repo_servers):
    """Test that DNF4 and DNF5 produce identical model.Package objects for the same packages."""
    testutil_dnf4 = pytest.importorskip("osbuild.testutil.dnf4")
    dnf4_solver = pytest.importorskip("osbuild.solver.dnf")
    testutil_dnf5 = pytest.importorskip("osbuild.testutil.dnf5")
    dnf5_solver = pytest.importorskip("osbuild.solver.dnf5")

    dnf4_pkgset = testutil_dnf4.depsolve_pkgset(repo_servers, ["bash", "pkg-with-no-deps"])
    _, dnf5_pkgset = testutil_dnf5.depsolve_pkgset(repo_servers, ["bash", "pkg-with-no-deps"])

    # NB: DNF4 and DNF5 produce package set in different order, we need to sort them
    dnf4_pkgset = sorted(dnf4_pkgset, key=lambda x: x.name)
    dnf5_pkgset = sorted(dnf5_pkgset, key=lambda x: x.get_name())

    for dnf4_pkg, dnf5_pkg in zip(dnf4_pkgset, dnf5_pkgset):
        # pylint: disable=protected-access
        rpm_pkg4 = dnf4_solver._dnf_pkg_to_package(dnf4_pkg)
        rpm_pkg5 = dnf5_solver._dnf_pkg_to_package(dnf5_pkg)
        assert_object_equal(rpm_pkg4, rpm_pkg5)


def test_dnf4_repo_config_to_repository():
    """Test DNF4 conversion of DNF repository to model.Repository object."""
    testutil_dnf4 = pytest.importorskip("osbuild.testutil.dnf4")
    dnf4_solver = pytest.importorskip("osbuild.solver.dnf")

    dnf_pkgset = testutil_dnf4.depsolve_pkgset(TEST_REPO_SERVERS, ["bash"])
    dnf_repo = list(dnf_pkgset)[0].repo

    # pylint: disable=protected-access
    repository = dnf4_solver._dnf_repo_to_repository(dnf_repo, "", [r["name"] for r in TEST_REPO_SERVERS])
    assert_object_equal(repository, TEST_REPOSITORY)


def test_dnf5_repo_config_to_repository():
    """Test DNF5 conversion of DNF repository to model.Repository object."""
    testutil_dnf5 = pytest.importorskip("osbuild.testutil.dnf5")
    dnf5_solver = pytest.importorskip("osbuild.solver.dnf5")

    _, dnf_pkgset = testutil_dnf5.depsolve_pkgset(TEST_REPO_SERVERS, ["bash"])
    dnf_repo = list(dnf_pkgset)[0].get_repo()

    # pylint: disable=protected-access
    repository = dnf5_solver._dnf_repo_to_repository(dnf_repo, "", [r["name"] for r in TEST_REPO_SERVERS])
    assert_object_equal(repository, TEST_REPOSITORY)
