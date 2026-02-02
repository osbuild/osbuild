# pylint: disable=too-many-lines
from datetime import datetime, timezone

import pytest

from osbuild.solver.api import (
    SolverAPIVersion,
    parse_request,
    serialize_response_depsolve,
    serialize_response_dump,
    serialize_response_search,
)
from osbuild.solver.api.v2 import _transactions_to_disjoint_sets
from osbuild.solver.api.v2 import parse_request as parse_request_v2
from osbuild.solver.api.v2 import serialize_response_depsolve as serialize_response_depsolve_v2
from osbuild.solver.api.v2 import serialize_response_dump as serialize_response_dump_v2
from osbuild.solver.api.v2 import serialize_response_search as serialize_response_search_v2
from osbuild.solver.exceptions import InvalidRequestError
from osbuild.solver.model import (
    Checksum,
    Dependency,
    DepsolveResult,
    DumpResult,
    Package,
    Repository,
    SearchResult,
)
from osbuild.solver.request import (
    DepsolveCmdArgs,
    DepsolveTransaction,
    SBOMRequest,
    SearchCmdArgs,
    SolverCommand,
    SolverConfig,
    SolverRequest,
)

from .conftest import assert_object_equal

TEST_CHECKSUM = Checksum("sha256", "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef")

TEST_PACKAGES = [
    Package(
        "PackageA",
        "1.0.0",
        "1.fc40",
        "x86_64",
        epoch=0,
        group="core",
        download_size=1000,
        install_size=1000,
        license="GPL-2.0-only",
        source_rpm="PackageA-1.0.0-1.fc40.src.rpm",
        build_time=1714857600,
        packager="John Foo <john.foo@example.com>",
        vendor="Example Inc.",
        url="https://example.com/packagea",
        summary="Package A",
        description="Package A is a package",
        provides=[Dependency("PackageA", "=", "1.0.0")],
        requires=[
            Dependency("PackageB", ">=", "2.0.0"),
            Dependency("PackageC", ">=", "3.0.0"),
        ],
        requires_pre=[Dependency("PackageC", ">=", "3.0.0")],
        conflicts=[Dependency("PackageD", ">= 5.0.0")],
        obsoletes=[Dependency("PackageE", ">= 6.0.0")],
        regular_requires=[Dependency("PackageB", ">=", "2.0.0")],
        recommends=[Dependency("PackageF", ">= 8.0.0")],
        suggests=[Dependency("PackageG", ">= 9.0.0")],
        enhances=[Dependency("PackageH", ">= 10.0.0")],
        supplements=[Dependency("PackageI", ">= 11.0.0")],
        files=[
            "/usr/bin/packagea",
            "/usr/share/packagea/README",
        ],
        location="Packages/PackageA-1.0.0-1.fc40.x86_64.rpm",
        remote_locations=["https://example.com/repo1/Packages/PackageA-1.0.0-1.fc40.x86_64.rpm"],
        checksum=TEST_CHECKSUM,
        header_checksum=TEST_CHECKSUM,
        repo_id="repo1"
    ),
    Package(
        "PackageB",
        "2.0.0",
        "2.fc40",
        "x86_64",
        epoch=2,
        group="core",
        download_size=2000,
        install_size=2000,
        license="GPL-2.0-only",
        source_rpm="PackageB-2.0.0-2.fc40.src.rpm",
        build_time=1714857600,
        packager="John Foo <john.foo@example.com>",
        vendor="Example Inc.",
        url="https://example.com/packageb",
        summary="Package B",
        description="Package B is a package",
        provides=[Dependency("PackageB", "=", "2.0.0")],
        files=[
            "/usr/bin/packageb",
            "/usr/share/packageb/README",
        ],
        location="Packages/PackageB-2.0.0-2.fc40.x86_64.rpm",
        remote_locations=["https://example.com/repo2/Packages/PackageB-2.0.0-2.fc40.x86_64.rpm"],
        checksum=TEST_CHECKSUM,
        header_checksum=TEST_CHECKSUM,
        repo_id="repo2",
    ),
    Package(
        "PackageC",
        "3.0.0",
        "3.fc40",
        "x86_64",
        epoch=3,
        group="core",
        download_size=3000,
        install_size=3000,
        license="GPL-2.0-only",
        source_rpm="PackageC-3.0.0-3.fc40.src.rpm",
        build_time=1714857600,
        packager="John Foo <john.foo@example.com>",
        vendor="Example Inc.",
        url="https://example.com/packagec",
        summary="Package C",
        description="Package C is a package",
        provides=[Dependency("PackageC", "=", "3.0.0")],
        files=[
            "/usr/bin/packagec",
            "/usr/share/packagec/README",
        ],
        location="Packages/PackageC-3.0.0-3.fc40.x86_64.rpm",
        remote_locations=["https://example.com/repo1/Packages/PackageC-3.0.0-3.fc40.x86_64.rpm"],
        checksum=TEST_CHECKSUM,
        header_checksum=TEST_CHECKSUM,
        repo_id="repo1",
    ),
    Package(
        "PackageD",
        "4.0.0",
        "4.fc40",
        "x86_64",
        epoch=4,
        group="core",
        download_size=4000,
        install_size=4000,
        license="GPL-2.0-only",
        source_rpm="PackageD-4.0.0-4.fc40.src.rpm",
        build_time=1714857600,
        packager="John Foo <john.foo@example.com>",
        vendor="Example Inc.",
        summary="Package D",
        description="Package D is a package",
        provides=[Dependency("PackageD", "=", "4.0.0")],
        files=[
            "/usr/bin/packaged",
            "/usr/share/packaged/README",
        ],
        location="Packages/PackageD-4.0.0-4.fc40.x86_64.rpm",
        remote_locations=["https://example.com/repo1/Packages/PackageD-4.0.0-4.fc40.x86_64.rpm"],
        checksum=TEST_CHECKSUM,
        header_checksum=TEST_CHECKSUM,
        repo_id="repo1",
    ),
]

TEST_REPOSITORIES = [
    Repository(
        "repo1",
        baseurl=["https://example.com/repo1"],
        name="Repo 1",
        metalink="https://example.com/repo1/metalink",
        mirrorlist="https://example.com/repo1/mirrorlist",
        gpgcheck=True,
        repo_gpgcheck=True,
        gpgkey=["https://example.com/repo1/RPM-GPG-KEY"],
        sslverify=True,
        sslcacert="https://example.com/repo1/ca.crt",
        sslclientkey="https://example.com/repo1/client.key",
        sslclientcert="https://example.com/repo1/client.crt",
    ),
    Repository(
        "repo2",
        baseurl=["https://example.com/repo2"],
        name="Repo 2",
        metalink="https://example.com/repo2/metalink",
        mirrorlist="https://example.com/repo2/mirrorlist",
        gpgcheck=False,
        repo_gpgcheck=True,
        gpgkey=["https://example.com/repo2/RPM-GPG-KEY"],
        sslverify=False,
        sslcacert="https://example.com/repo2/ca.crt",
        sslclientkey="https://example.com/repo2/client.key",
        sslclientcert="https://example.com/repo2/client.crt",
    ),
]


def test_transactions_to_disjoint_sets():
    """
    Test that the _transactions_to_disjoint_sets function converts a list
    of transactions to a list of disjoint sets of packages.
    """
    transactions = [
        [TEST_PACKAGES[0]],
        [TEST_PACKAGES[0], TEST_PACKAGES[2]],
        TEST_PACKAGES,
    ]
    disjoint_sets = _transactions_to_disjoint_sets(transactions)
    assert disjoint_sets == [
        [TEST_PACKAGES[0]],
        [TEST_PACKAGES[2]],
        [TEST_PACKAGES[1], TEST_PACKAGES[3]],
    ]


def assert_serialized_package(pkg: dict, package: Package):
    """
    Assert that a serialized package dict matches the Package object for V2 API.

    NOTE: This check validates that the V2 API returns all current Package model
    attributes. If a new attribute is added to the Package model, this test will
    fail. In that case, do NOT simply extend the V2 API serialization - instead,
    consider creating a new API version (V3) to expose the new attribute; or
    modifying this test for the unexposed attribute. This test exists to ensure
    the current V2 implementation remains stable and complete.
    """
    expected_pkg_keys = [attr for attr in package.__dict__.keys() if not attr.startswith("_")]
    expected_pkg_keys.sort()
    assert sorted(list(pkg.keys())) == expected_pkg_keys

    # Core fields
    assert pkg["name"] == package.name
    assert pkg["epoch"] == package.epoch
    assert pkg["version"] == package.version
    assert pkg["release"] == package.release
    assert pkg["arch"] == package.arch
    assert pkg["repo_id"] == package.repo_id
    assert pkg["location"] == package.location
    assert pkg["remote_locations"] == package.remote_locations

    # Checksum fields (dicts with algorithm and value)
    if package.checksum:
        assert pkg["checksum"] == {"algorithm": package.checksum.algorithm, "value": package.checksum.value}
    else:
        assert pkg["checksum"] is None

    if package.header_checksum:
        assert pkg["header_checksum"] == {
            "algorithm": package.header_checksum.algorithm,
            "value": package.header_checksum.value,
        }
    else:
        assert pkg["header_checksum"] is None

    # Metadata fields (may be None)
    assert pkg["license"] == package.license
    assert pkg["summary"] == package.summary
    assert pkg["description"] == package.description
    assert pkg["url"] == package.url
    assert pkg["vendor"] == package.vendor
    assert pkg["packager"] == package.packager
    assert pkg["download_size"] == package.download_size
    assert pkg["install_size"] == package.install_size
    assert pkg["group"] == package.group
    assert pkg["source_rpm"] == package.source_rpm
    assert pkg["reason"] == package.reason

    # build_time is converted to RFC3339 string
    if package.build_time:
        assert pkg["build_time"] == datetime.fromtimestamp(
            package.build_time, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    else:
        assert pkg["build_time"] is None

    # Helper to convert Dependency to dict (matching _dependency_as_dict)
    def dep_to_dict(dep):
        d = {"name": dep.name}
        if dep.relation:
            d["relation"] = dep.relation
        if dep.version:
            d["version"] = dep.version
        return d

    # Dependency lists (always arrays, may be empty)
    assert pkg["provides"] == [dep_to_dict(dep) for dep in package.provides]
    assert pkg["requires"] == [dep_to_dict(dep) for dep in package.requires]
    assert pkg["requires_pre"] == [dep_to_dict(dep) for dep in package.requires_pre]
    assert pkg["conflicts"] == [dep_to_dict(dep) for dep in package.conflicts]
    assert pkg["obsoletes"] == [dep_to_dict(dep) for dep in package.obsoletes]
    assert pkg["regular_requires"] == [dep_to_dict(dep) for dep in package.regular_requires]
    assert pkg["recommends"] == [dep_to_dict(dep) for dep in package.recommends]
    assert pkg["suggests"] == [dep_to_dict(dep) for dep in package.suggests]
    assert pkg["enhances"] == [dep_to_dict(dep) for dep in package.enhances]
    assert pkg["supplements"] == [dep_to_dict(dep) for dep in package.supplements]

    # File list (always array, may be empty)
    assert pkg["files"] == package.files


def assert_serialized_repository(repo: dict, repository: Repository):
    """Assert that a serialized repository dict matches the Repository object for V2 API.

    NOTE: This check validates that the V2 API returns all current Repository model
    attributes. If a new attribute is added to the Repository model, this test will
    fail. In that case, do NOT simply extend the V2 API serialization - instead,
    consider creating a new API version (V3) to expose the new attribute; or
    modifying this test for the unexposed attribute. This test exists to ensure
    the current V2 implementation remains stable and complete.
    """
    # Build expected keys from model attributes
    expected_keys = [attr for attr in vars(repository) if not attr.startswith("_")]
    # repo_id is serialized as "id" in the dict
    expected_keys = ["id" if k == "repo_id" else k for k in expected_keys]
    # These fields are input-only (used by solver but not serialized in response)
    input_only_fields = ["password", "enabled", "priority", "username", "skip_if_unavailable"]
    expected_keys = [k for k in expected_keys if k not in input_only_fields]

    # All fields should always be present (consistent schema)
    assert sorted(repo.keys()) == sorted(expected_keys)

    # NOTE: dict uses "id" but Repository uses "repo_id"
    assert repo["id"] == repository.repo_id
    assert repo["name"] == repository.name
    assert repo["baseurl"] == repository.baseurl
    assert repo["metalink"] == repository.metalink
    assert repo["mirrorlist"] == repository.mirrorlist
    assert repo["gpgcheck"] == repository.gpgcheck
    assert repo["repo_gpgcheck"] == repository.repo_gpgcheck
    assert repo["gpgkey"] == repository.gpgkey
    assert repo["sslverify"] == repository.sslverify
    assert repo["metadata_expire"] == repository.metadata_expire
    assert repo["module_hotfixes"] == repository.module_hotfixes
    assert repo["rhsm"] == repository.rhsm

    # SSL fields are None when rhsm=True (secrets not exposed), otherwise actual values
    if repository.rhsm:
        assert repo["sslcacert"] is None
        assert repo["sslclientkey"] is None
        assert repo["sslclientcert"] is None
    else:
        assert repo["sslcacert"] == repository.sslcacert
        assert repo["sslclientkey"] == repository.sslclientkey
        assert repo["sslclientcert"] == repository.sslclientcert


@pytest.mark.parametrize("serializer,result_class", [
    pytest.param(serialize_response_dump_v2, DumpResult, id="dump_v2"),
    pytest.param(serialize_response_search_v2, SearchResult, id="search_v2"),
    pytest.param(
        lambda solver, result: serialize_response_dump(SolverAPIVersion.V2, solver, result),
        DumpResult,
        id="dump",
    ),
    pytest.param(
        lambda solver, result: serialize_response_search(SolverAPIVersion.V2, solver, result),
        SearchResult,
        id="search"
    ),
])
def test_solver_response_v2_dump_search(serializer, result_class):
    solver_name = "solver_name"
    response = serializer(solver_name, result_class(TEST_PACKAGES, TEST_REPOSITORIES))
    assert isinstance(response, dict)

    assert sorted(list(response.keys())) == [
        "packages",
        "repos",
        "solver",
    ]
    assert response["solver"] == solver_name

    assert len(response["packages"]) == len(TEST_PACKAGES)
    for idx, pkg in enumerate(response["packages"]):
        assert_serialized_package(pkg, TEST_PACKAGES[idx])

    assert len(response["repos"]) == len(TEST_REPOSITORIES)
    for idx, (repo_id, repo) in enumerate(response["repos"].items()):
        assert repo_id == TEST_REPOSITORIES[idx].repo_id
        assert_serialized_repository(repo, TEST_REPOSITORIES[idx])


@pytest.mark.parametrize("modules", [
    pytest.param(None, id="no-modules"),
    pytest.param({"module1": "solver specific data"}, id="with-modules"),
])
@pytest.mark.parametrize("sbom", [
    pytest.param(None, id="no-sbom"),
    pytest.param({"sbom": "sbom document"}, id="with-sbom"),
])
@pytest.mark.parametrize("serializer", [
    pytest.param(serialize_response_depsolve_v2, id="depsolve_v2"),
    pytest.param(
        lambda solver, result: serialize_response_depsolve(SolverAPIVersion.V2, solver, result),
        id="depsolve",
    ),
])
def test_solver_response_v2_depsolve(modules, sbom, serializer):
    # NOTE: each transaction contains a superset of the previous transaction.
    transactions_result = [
        [TEST_PACKAGES[0]],
        [TEST_PACKAGES[0], TEST_PACKAGES[2]],
        TEST_PACKAGES,
    ]
    # NOTE: the serialized transactions should be disjoint sets of packages.
    transactions_serialized_expected = [
        [TEST_PACKAGES[0]],
        [TEST_PACKAGES[2]],
        [TEST_PACKAGES[1], TEST_PACKAGES[3]],
    ]
    solver_name = "solver_name"
    response = serializer(
        solver_name,
        DepsolveResult(
            transactions_result,
            TEST_REPOSITORIES,
            modules,
            sbom,
        )
    )

    expected_keys = ["modules", "repos", "solver", "transactions"]
    if sbom:
        expected_keys.append("sbom")
        assert response["sbom"] == sbom
    assert sorted(list(response.keys())) == sorted(expected_keys)

    assert response["solver"] == solver_name

    expected_modules = modules or {}
    assert response["modules"] == expected_modules

    assert len(response["transactions"]) == len(transactions_result)
    # NOTE: the sum of the packages in all transactions should be equal to the total number of packages
    # (the last transaction result in DepsolveResult.transactions).
    assert sum(len(transaction) for transaction in response["transactions"]) == len(TEST_PACKAGES)
    for idx, transaction in enumerate(response["transactions"]):
        for pkg, expected_pkg in zip(transaction, transactions_serialized_expected[idx]):
            assert_serialized_package(pkg, expected_pkg)

    assert len(response["repos"]) == len(TEST_REPOSITORIES)
    for idx, (repo_id, repo) in enumerate(response["repos"].items()):
        assert repo_id == TEST_REPOSITORIES[idx].repo_id
        assert_serialized_repository(repo, TEST_REPOSITORIES[idx])


@pytest.mark.parametrize("request_dict,expected_result,expected_error", [
    # Valid DEPSOLVE request - minimal
    pytest.param(
        {
            "api_version": 2,
            "command": "depsolve",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
                "transactions": [{"package-specs": ["bash", "vim"]}],
            },
        },
        SolverRequest(
            api_version=SolverAPIVersion.V2,
            command=SolverCommand.DEPSOLVE,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[Repository.from_request(repo_id="fedora", baseurl=["https://example.com/fedora"])],
            ),
            depsolve_args=DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash", "vim"])]),
        ),
        None,
        id="valid_depsolve_minimal",
    ),
    # Valid DEPSOLVE request - full
    pytest.param(
        {
            "api_version": 2,
            "command": "depsolve",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "module_platform_id": "platform:f43",
            "proxy": "http://proxy.example.com:8080",
            "arguments": {
                "repos": [
                    {
                        "id": "fedora",
                        "name": "Fedora 43",
                        "baseurl": ["https://example.com/fedora"],
                        "metalink": "https://example.com/fedora/metalink",
                        "mirrorlist": "https://example.com/fedora/mirrorlist",
                        "gpgcheck": True,
                        "repo_gpgcheck": True,
                        "gpgkey": [
                            "https://example.com/fedora/RPM-GPG-KEY",
                            "https://example.com/fedora/RPM-GPG-KEY-2",
                        ],
                        "sslverify": False,
                        "sslcacert": "/etc/pki/ca.crt",
                        "sslclientkey": "/etc/pki/client.key",
                        "sslclientcert": "/etc/pki/client.crt",
                        "metadata_expire": "1h",
                        "module_hotfixes": True,
                    },
                ],
                "transactions": [
                    {
                        "package-specs": ["bash", "vim"],
                        "exclude-specs": ["emacs"],
                        "repo-ids": ["fedora"],
                        "module-enable-specs": ["nodejs:18"],
                        "install_weak_deps": True,
                    },
                ],
                "optional-metadata": ["filelists", "other"],
                "sbom": {"type": "spdx"},
            },
        },
        SolverRequest(
            api_version=SolverAPIVersion.V2,
            command=SolverCommand.DEPSOLVE,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                module_platform_id="platform:f43",
                proxy="http://proxy.example.com:8080",
                repos=[
                    Repository.from_request(
                        repo_id="fedora",
                        name="Fedora 43",
                        baseurl=["https://example.com/fedora"],
                        metalink="https://example.com/fedora/metalink",
                        mirrorlist="https://example.com/fedora/mirrorlist",
                        gpgcheck=True,
                        repo_gpgcheck=True,
                        gpgkey=[
                            "https://example.com/fedora/RPM-GPG-KEY",
                            "https://example.com/fedora/RPM-GPG-KEY-2",
                        ],
                        sslverify=False,
                        sslcacert="/etc/pki/ca.crt",
                        sslclientkey="/etc/pki/client.key",
                        sslclientcert="/etc/pki/client.crt",
                        metadata_expire="1h",
                        module_hotfixes=True,
                    ),
                ],
                optional_metadata=["filelists", "other"],
            ),
            depsolve_args=DepsolveCmdArgs(
                transactions=[
                    DepsolveTransaction(
                        package_specs=["bash", "vim"],
                        exclude_specs=["emacs"],
                        repo_ids=["fedora"],
                        module_enable_specs=["nodejs:18"],
                        install_weak_deps=True,
                    ),
                ],
                sbom_request=SBOMRequest("spdx"),
            ),
        ),
        None,
        id="valid_depsolve_full",
    ),
    # Valid DEPSOLVE with multiple transactions
    pytest.param(
        {
            "api_version": 2,
            "command": "depsolve",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
                "transactions": [
                    {"package-specs": ["bash"]},
                    {"package-specs": ["vim", "emacs"]},
                ],
            },
        },
        SolverRequest(
            api_version=SolverAPIVersion.V2,
            command=SolverCommand.DEPSOLVE,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[Repository.from_request(repo_id="fedora", baseurl=["https://example.com/fedora"])],
            ),
            depsolve_args=DepsolveCmdArgs([
                DepsolveTransaction(package_specs=["bash"]),
                DepsolveTransaction(package_specs=["vim", "emacs"]),
            ]),
        ),
        None,
        id="valid_depsolve_multiple_transactions",
    ),
    # Valid DEPSOLVE with root_dir
    pytest.param(
        {
            "api_version": 2,
            "command": "depsolve",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "root_dir": "/mnt/sysroot",
                "transactions": [{"package-specs": ["bash"]}],
            },
        },
        SolverRequest(
            api_version=SolverAPIVersion.V2,
            command=SolverCommand.DEPSOLVE,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                root_dir="/mnt/sysroot",
            ),
            depsolve_args=DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
        ),
        None,
        id="valid_depsolve_with_root_dir",
    ),
    # Valid DUMP request
    pytest.param(
        {
            "api_version": 2,
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
            },
        },
        SolverRequest(
            api_version=SolverAPIVersion.V2,
            command=SolverCommand.DUMP,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[Repository.from_request(repo_id="fedora", baseurl=["https://example.com/fedora"])],
            ),
        ),
        None,
        id="valid_dump",
    ),
    # Valid SEARCH request
    pytest.param(
        {
            "api_version": 2,
            "command": "search",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
                "search": {
                    "packages": ["bash", "vim"],
                    "latest": True,
                },
            },
        },
        SolverRequest(
            api_version=SolverAPIVersion.V2,
            command=SolverCommand.SEARCH,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[Repository.from_request(repo_id="fedora", baseurl=["https://example.com/fedora"])],
            ),
            search_args=SearchCmdArgs(packages=["bash", "vim"], latest=True),
        ),
        None,
        id="valid_search_with_latest",
    ),
    # Valid SEARCH request without latest flag
    pytest.param(
        {
            "api_version": 2,
            "command": "search",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
                "search": {
                    "packages": ["bash"],
                },
            },
        },
        SolverRequest(
            api_version=SolverAPIVersion.V2,
            command=SolverCommand.SEARCH,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[Repository.from_request(repo_id="fedora", baseurl=["https://example.com/fedora"])],
            ),
            search_args=SearchCmdArgs(packages=["bash"], latest=False),
        ),
        None,
        id="valid_search_without_latest",
    ),
    # Valid request with multiple repos
    pytest.param(
        {
            "api_version": 2,
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [
                    {
                        "id": "fedora",
                        "baseurl": ["https://example.com/fedora"],
                        "gpgkey": [
                            "https://example.com/fedora/RPM-GPG-KEY-1",
                            "https://example.com/fedora/RPM-GPG-KEY-2",
                        ],
                    },
                    {
                        "id": "updates",
                        "metalink": "https://example.com/updates/metalink",
                    },
                ],
            },
        },
        SolverRequest(
            api_version=SolverAPIVersion.V2,
            command=SolverCommand.DUMP,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[
                    Repository.from_request(
                        repo_id="fedora",
                        baseurl=["https://example.com/fedora"],
                        gpgkey=[
                            "https://example.com/fedora/RPM-GPG-KEY-1",
                            "https://example.com/fedora/RPM-GPG-KEY-2",
                        ],
                    ),
                    Repository.from_request(
                        repo_id="updates",
                        metalink="https://example.com/updates/metalink",
                    ),
                ],
            ),
        ),
        None,
        id="valid_multiple_repos",
    ),
    # Valid request with sslverify default (True)
    pytest.param(
        {
            "api_version": 2,
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
            },
        },
        SolverRequest(
            api_version=SolverAPIVersion.V2,
            command=SolverCommand.DUMP,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[Repository.from_request(repo_id="fedora", baseurl=["https://example.com/fedora"])],
            ),
        ),
        None,
        id="valid_sslverify_default",
    ),
    # Valid request with optional-metadata
    pytest.param(
        {
            "api_version": 2,
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
                "optional-metadata": ["filelists", "other"],
            },
        },
        SolverRequest(
            api_version=SolverAPIVersion.V2,
            command=SolverCommand.DUMP,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[Repository.from_request(repo_id="fedora", baseurl=["https://example.com/fedora"])],
                optional_metadata=["filelists", "other"],
            ),
        ),
        None,
        id="valid_with_optional_metadata",
    ),
    # Valid request with gpgkey as list
    pytest.param(
        {
            "api_version": 2,
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [
                    {
                        "id": "fedora",
                        "baseurl": ["https://example.com/fedora"],
                        "gpgkey": ["https://example.com/fedora/RPM-GPG-KEY"],
                    },
                ],
            },
        },
        SolverRequest(
            api_version=SolverAPIVersion.V2,
            command=SolverCommand.DUMP,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[
                    Repository.from_request(
                        repo_id="fedora",
                        baseurl=["https://example.com/fedora"],
                        gpgkey=["https://example.com/fedora/RPM-GPG-KEY"],
                    ),
                ],
            ),
        ),
        None,
        id="valid_gpgkey_list",
    ),
    # Valid request with rhsm=True
    pytest.param(
        {
            "api_version": 2,
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [
                    {
                        "id": "rhel",
                        "baseurl": ["https://cdn.redhat.com/content/rhel"],
                        "rhsm": True,
                    },
                ],
            },
        },
        SolverRequest(
            api_version=SolverAPIVersion.V2,
            command=SolverCommand.DUMP,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[
                    Repository.from_request(
                        repo_id="rhel",
                        baseurl=["https://cdn.redhat.com/content/rhel"],
                        rhsm=True,
                    ),
                ],
            ),
        ),
        None,
        id="valid_rhsm_repository",
    ),
    # Invalid: missing 'command'
    pytest.param(
        {
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {},
        },
        None,
        "Missing required field 'command'",
        id="invalid_missing_command",
    ),
    # Invalid: missing 'arch'
    pytest.param(
        {
            "command": "dump",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {},
        },
        None,
        "Missing required field 'arch'",
        id="invalid_missing_arch",
    ),
    # Invalid: missing 'releasever'
    pytest.param(
        {
            "api_version": 2,
            "command": "dump",
            "arch": "x86_64",
            "cachedir": "/tmp/cache",
            "arguments": {},
        },
        None,
        "Missing required field 'releasever'",
        id="invalid_missing_releasever",
    ),
    # Invalid: missing 'cachedir'
    pytest.param(
        {
            "api_version": 2,
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "arguments": {},
        },
        None,
        "Missing required field 'cachedir'",
        id="invalid_missing_cachedir",
    ),
    # Invalid: missing 'arguments'
    pytest.param(
        {
            "api_version": 2,
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
        },
        None,
        "Missing required field 'arguments'",
        id="invalid_missing_arguments",
    ),
    # Invalid: invalid command
    pytest.param(
        {
            "api_version": 2,
            "command": "invalid_command",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {},
        },
        None,
        "Invalid command 'invalid_command'",
        id="invalid_command",
    ),
    # Invalid: arguments not a dict
    pytest.param(
        {
            "api_version": 2,
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": "not a dict",
        },
        None,
        "Field 'arguments' must be a dict",
        id="invalid_arguments_not_dict",
    ),
    # Invalid: repos not a list
    pytest.param(
        {
            "api_version": 2,
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": "not a list",
            },
        },
        None,
        "Field 'repos' must be a list",
        id="invalid_repos_not_list",
    ),
    # Invalid: repo config not a dict
    pytest.param(
        {
            "api_version": 2,
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": ["not a dict"],
            },
        },
        None,
        "Repository config must be a dict",
        id="invalid_repo_not_dict",
    ),
    # Invalid: repo missing 'id'
    pytest.param(
        {
            "api_version": 2,
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"baseurl": ["https://example.com/fedora"]}],
            },
        },
        None,
        "Missing required field 'id' in 'repos' item configuration",
        id="invalid_repo_missing_id",
    ),
    # Invalid: transactions not a list
    pytest.param(
        {
            "api_version": 2,
            "command": "depsolve",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
                "transactions": "not a list",
            },
        },
        None,
        "Field 'transactions' must be a list",
        id="invalid_transactions_not_list",
    ),
    # Invalid: transaction not a dict
    pytest.param(
        {
            "api_version": 2,
            "command": "depsolve",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
                "transactions": ["not a dict"],
            },
        },
        None,
        "Depsolve transaction must be a dict",
        id="invalid_transaction_not_dict",
    ),
    # Invalid: transaction with empty package-specs
    pytest.param(
        {
            "api_version": 2,
            "command": "depsolve",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
                "transactions": [{"package-specs": []}],
            },
        },
        None,
        "Depsolve transaction must contain at least one package specification",
        id="invalid_transaction_empty_package_specs",
    ),
    # Invalid: search not a dict
    pytest.param(
        {
            "api_version": 2,
            "command": "search",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
                "search": "not a dict",
            },
        },
        None,
        "Field 'search' must be a dict",
        id="invalid_search_not_dict",
    ),
    # Invalid: search packages not a list
    pytest.param(
        {
            "api_version": 2,
            "command": "search",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
                "search": {
                    "packages": "not a list",
                },
            },
        },
        None,
        "Field 'packages' must be a list",
        id="invalid_search_packages_not_list",
    ),
    # Invalid: search missing packages
    pytest.param(
        {
            "api_version": 2,
            "command": "search",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
                "search": {},
            },
        },
        None,
        "Missing required field 'packages' in 'search' dict",
        id="invalid_search_missing_packages",
    ),
    # Invalid: sbom not a dict
    pytest.param(
        {
            "api_version": 2,
            "command": "depsolve",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
                "transactions": [{"package-specs": ["bash"]}],
                "sbom": "not a dict",
            },
        },
        None,
        "Field 'sbom' must be a dict",
        id="invalid_sbom_not_dict",
    ),
    # Invalid: sbom missing type
    pytest.param(
        {
            "api_version": 2,
            "command": "depsolve",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
                "transactions": [{"package-specs": ["bash"]}],
                "sbom": {},
            },
        },
        None,
        "Missing required field 'type' in 'sbom'",
        id="invalid_sbom_missing_type",
    ),
    # Invalid: optional-metadata not a list
    pytest.param(
        {
            "api_version": 2,
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
                "optional-metadata": "not a list",
            },
        },
        None,
        "Field 'optional-metadata' must be a list",
        id="invalid_optional_metadata_not_list",
    ),
    # Invalid: baseurl not a list
    pytest.param(
        {
            "api_version": 2,
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": "https://example.com/fedora"}],
            },
        },
        None,
        "'baseurl' must be a list of URLs",
        id="invalid_baseurl_not_list",
    ),
    # Invalid: gpgkey not a list (V2 requires list, unlike V1 which accepts string)
    pytest.param(
        {
            "api_version": 2,
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [
                    {
                        "id": "fedora",
                        "baseurl": ["https://example.com/fedora"],
                        "gpgkey": "https://example.com/fedora/RPM-GPG-KEY",
                    },
                ],
            },
        },
        None,
        "'gpgkey' must be a list",
        id="invalid_gpgkey_not_list",
    ),
])
@pytest.mark.parametrize("parser", [
    pytest.param(parse_request_v2, id="parse_request_v2"),
    pytest.param(parse_request, id="parse_request"),
])
def test_parse_request_v2(request_dict, expected_result, expected_error, parser):
    """Test parse_request function with various valid and invalid inputs"""
    if expected_error:
        with pytest.raises(InvalidRequestError, match=expected_error):
            parser(request_dict)
    else:
        result = parser(request_dict)
        assert_object_equal(result, expected_result)


@pytest.mark.parametrize("repositories,expected_ssl_values", [
    # Single RHSM repository - SSL secrets should be None
    pytest.param(
        [
            Repository(
                "rhel",
                baseurl=["https://cdn.redhat.com/content/rhel"],
                name="RHEL",
                rhsm=True,
                sslcacert="/etc/rhsm/ca/redhat-uep.pem",
                sslclientkey="/etc/pki/entitlement/key.pem",
                sslclientcert="/etc/pki/entitlement/cert.pem",
            ),
        ],
        {
            "rhel": {"rhsm": True, "sslcacert": None, "sslclientkey": None, "sslclientcert": None},
        },
        id="rhsm_repo_nulls_ssl_secrets",
    ),
    # Single non-RHSM repository - SSL secrets should have actual values
    pytest.param(
        [
            Repository(
                "fedora",
                baseurl=["https://example.com/fedora"],
                name="Fedora",
                rhsm=False,
                sslcacert="/etc/pki/ca.crt",
                sslclientkey="/etc/pki/client.key",
                sslclientcert="/etc/pki/client.crt",
            ),
        ],
        {
            "fedora": {
                "rhsm": False,
                "sslcacert": "/etc/pki/ca.crt",
                "sslclientkey": "/etc/pki/client.key",
                "sslclientcert": "/etc/pki/client.crt",
            },
        },
        id="non_rhsm_repo_includes_ssl_values",
    ),
    # Mixed RHSM and non-RHSM repositories
    pytest.param(
        [
            Repository(
                "rhel",
                baseurl=["https://cdn.redhat.com/content/rhel"],
                name="RHEL",
                rhsm=True,
                sslcacert="/etc/rhsm/ca/redhat-uep.pem",
                sslclientkey="/etc/pki/entitlement/key.pem",
                sslclientcert="/etc/pki/entitlement/cert.pem",
            ),
            Repository(
                "fedora",
                baseurl=["https://example.com/fedora"],
                name="Fedora",
                rhsm=False,
                sslcacert="/etc/pki/ca.crt",
                sslclientkey="/etc/pki/client.key",
                sslclientcert="/etc/pki/client.crt",
            ),
        ],
        {
            "rhel": {"rhsm": True, "sslcacert": None, "sslclientkey": None, "sslclientcert": None},
            "fedora": {
                "rhsm": False,
                "sslcacert": "/etc/pki/ca.crt",
                "sslclientkey": "/etc/pki/client.key",
                "sslclientcert": "/etc/pki/client.crt",
            },
        },
        id="mixed_rhsm_and_non_rhsm_repos",
    ),
])
def test_rhsm_ssl_secrets_handling(repositories, expected_ssl_values):
    """Test that RHSM repositories have SSL secrets set to None, while non-RHSM repos include actual values."""
    result = DepsolveResult([
        [TEST_PACKAGES[0]],
        [TEST_PACKAGES[0], TEST_PACKAGES[2]],
        TEST_PACKAGES,
    ], repositories)
    response = serialize_response_depsolve_v2("solver", result)

    assert len(response["repos"]) == len(repositories)

    for repo_id, expected in expected_ssl_values.items():
        assert repo_id in response["repos"], f"Repository '{repo_id}' not found in response"
        repo_dict = response["repos"][repo_id]

        assert repo_dict["rhsm"] == expected["rhsm"]
        assert repo_dict["sslcacert"] == expected["sslcacert"]
        assert repo_dict["sslclientkey"] == expected["sslclientkey"]
        assert repo_dict["sslclientcert"] == expected["sslclientcert"]
