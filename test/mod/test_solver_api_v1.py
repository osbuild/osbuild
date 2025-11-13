# pylint: disable=too-many-lines
from datetime import datetime, timezone

import pytest

from osbuild.solver import InvalidRequestError
from osbuild.solver.api import (
    SolverAPIVersion,
    parse_request,
    serialize_response_depsolve,
    serialize_response_dump,
    serialize_response_search,
)
from osbuild.solver.api.v1 import parse_request as parse_request_v1
from osbuild.solver.api.v1 import serialize_response_depsolve as serialize_response_depsolve_v1
from osbuild.solver.api.v1 import serialize_response_dump as serialize_response_dump_v1
from osbuild.solver.api.v1 import serialize_response_search as serialize_response_search_v1
from osbuild.solver.model import (
    Checksum,
    Dependency,
    Package,
    Repository,
)
from osbuild.solver.request import (
    DepsolveCmdArgs,
    DepsolveTransaction,
    RepositoryConfig,
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
        "Repo 1",
        baseurl=["https://example.com/repo1"],
        metalink="https://example.com/repo1/metalink",
        mirrorlist="https://example.com/repo1/mirrorlist",
        gpgcheck=True,
        repo_gpgcheck=True,
        gpgkeys=["https://example.com/repo1/RPM-GPG-KEY"],
        sslverify=True,
        sslcacert="https://example.com/repo1/ca.crt",
        sslclientkey="https://example.com/repo1/client.key",
        sslclientcert="https://example.com/repo1/client.crt",
    ),
    Repository(
        "repo2",
        "Repo 2",
        baseurl=["https://example.com/repo2"],
        metalink="https://example.com/repo2/metalink",
        mirrorlist="https://example.com/repo2/mirrorlist",
        gpgcheck=False,
        repo_gpgcheck=True,
        gpgkeys=["https://example.com/repo2/RPM-GPG-KEY"],
        sslverify=False,
        sslcacert="https://example.com/repo2/ca.crt",
        sslclientkey="https://example.com/repo2/client.key",
        sslclientcert="https://example.com/repo2/client.crt",
    ),
]


@pytest.mark.parametrize("serializer", [
    serialize_response_dump_v1,
    serialize_response_search_v1,
    lambda packages: serialize_response_dump(SolverAPIVersion.V1, packages),
    lambda packages: serialize_response_search(SolverAPIVersion.V1, packages),
], ids=["dump_v1", "search_v1", "dump", "search"])
def test_solver_response_v1_dump_search(serializer):
    response = serializer(TEST_PACKAGES)
    assert isinstance(response, list)
    assert len(response) == len(TEST_PACKAGES)
    for idx, pkg in enumerate(response):
        assert sorted(list(pkg.keys())) == [
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
        assert pkg["name"] == TEST_PACKAGES[idx].name
        assert pkg["summary"] == TEST_PACKAGES[idx].summary
        assert pkg["description"] == TEST_PACKAGES[idx].description
        assert pkg["url"] == TEST_PACKAGES[idx].url
        assert pkg["repo_id"] == TEST_PACKAGES[idx].repo_id
        assert pkg["epoch"] == TEST_PACKAGES[idx].epoch
        assert pkg["version"] == TEST_PACKAGES[idx].version
        assert pkg["release"] == TEST_PACKAGES[idx].release
        assert pkg["arch"] == TEST_PACKAGES[idx].arch
        assert pkg["buildtime"] == datetime.fromtimestamp(
            TEST_PACKAGES[idx].build_time, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        assert pkg["license"] == TEST_PACKAGES[idx].license


@pytest.mark.parametrize("modules", [
    None,
    {"module1": "solver specific data"}
], ids=["no-modules", "with-modules"])
@pytest.mark.parametrize("sbom", [None, {"sbom": "sbom document"}], ids=["no-sbom", "with-sbom"])
@pytest.mark.parametrize("solver", ["dnf5", "dnf"])
@pytest.mark.parametrize("serializer", [
    serialize_response_depsolve_v1,
    lambda solver, packages, repositories, modules, sbom: serialize_response_depsolve(
        SolverAPIVersion.V1, solver, packages, repositories, modules, sbom
    ),
], ids=["depsolve_v1", "depsolve"])
def test_solver_response_v1_depsolve(solver, modules, sbom, serializer):
    response = serializer(solver, TEST_PACKAGES, TEST_REPOSITORIES, modules, sbom)
    expected_keys = ["solver", "packages", "repos", "modules"]
    if sbom:
        expected_keys.append("sbom")
    assert list(response.keys()) == expected_keys

    if modules:
        assert response["modules"] == modules
    else:
        assert isinstance(response["modules"], dict)
        assert not response["modules"]

    if sbom:
        assert response["sbom"] == sbom

    assert response["solver"] == solver if solver else "unknown"
    assert len(response["packages"]) == len(TEST_PACKAGES)
    for idx, pkg in enumerate(response["packages"]):
        assert sorted(list(pkg.keys())) == [
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
        assert pkg["name"] == TEST_PACKAGES[idx].name
        assert pkg["epoch"] == TEST_PACKAGES[idx].epoch
        assert pkg["version"] == TEST_PACKAGES[idx].version
        assert pkg["release"] == TEST_PACKAGES[idx].release
        assert pkg["arch"] == TEST_PACKAGES[idx].arch
        assert pkg["repo_id"] == TEST_PACKAGES[idx].repo_id
        assert pkg["path"] == TEST_PACKAGES[idx].location
        assert pkg["remote_location"] == TEST_PACKAGES[idx].remote_locations[0]
        assert pkg["checksum"] == str(TEST_PACKAGES[idx].checksum)
    assert len(response["repos"]) == len(TEST_REPOSITORIES)
    assert isinstance(response["repos"], dict)
    for idx, repo in enumerate(response["repos"].values()):
        assert sorted(list(repo.keys())) == [
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
        assert repo["id"] == TEST_REPOSITORIES[idx].repo_id
        assert repo["name"] == TEST_REPOSITORIES[idx].name
        assert repo["baseurl"] == TEST_REPOSITORIES[idx].baseurl
        assert repo["metalink"] == TEST_REPOSITORIES[idx].metalink
        assert repo["mirrorlist"] == TEST_REPOSITORIES[idx].mirrorlist
        assert repo["gpgcheck"] == TEST_REPOSITORIES[idx].gpgcheck
        assert repo["repo_gpgcheck"] == TEST_REPOSITORIES[idx].repo_gpgcheck
        assert repo["gpgkeys"] == TEST_REPOSITORIES[idx].gpgkeys
        assert repo["sslverify"] == TEST_REPOSITORIES[idx].sslverify
        assert repo["sslcacert"] == TEST_REPOSITORIES[idx].sslcacert
        assert repo["sslclientkey"] == TEST_REPOSITORIES[idx].sslclientkey
        assert repo["sslclientcert"] == TEST_REPOSITORIES[idx].sslclientcert


@pytest.mark.parametrize("request_dict,expected_result,expected_error", [
    # Valid DEPSOLVE request - minimal
    pytest.param(
        {
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
            api_version=SolverAPIVersion.V1,
            command=SolverCommand.DEPSOLVE,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["https://example.com/fedora"])],
            ),
            depsolve_args=DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash", "vim"])]),
        ),
        None,
        id="valid_depsolve_minimal",
    ),
    # Valid DEPSOLVE request - full
    pytest.param(
        {
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
                        "gpgkey": "https://example.com/fedora/RPM-GPG-KEY",
                        "gpgkeys": ["https://example.com/fedora/RPM-GPG-KEY-2"],
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
            api_version=SolverAPIVersion.V1,
            command=SolverCommand.DEPSOLVE,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                module_platform_id="platform:f43",
                proxy="http://proxy.example.com:8080",
                repos=[
                    RepositoryConfig(
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
            api_version=SolverAPIVersion.V1,
            command=SolverCommand.DEPSOLVE,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["https://example.com/fedora"])],
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
            api_version=SolverAPIVersion.V1,
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
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
            },
        },
        SolverRequest(
            api_version=SolverAPIVersion.V1,
            command=SolverCommand.DUMP,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["https://example.com/fedora"])],
            ),
        ),
        None,
        id="valid_dump",
    ),
    # Valid SEARCH request
    pytest.param(
        {
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
            api_version=SolverAPIVersion.V1,
            command=SolverCommand.SEARCH,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["https://example.com/fedora"])],
            ),
            search_args=SearchCmdArgs(packages=["bash", "vim"], latest=True),
        ),
        None,
        id="valid_search_with_latest",
    ),
    # Valid SEARCH request without latest flag
    pytest.param(
        {
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
            api_version=SolverAPIVersion.V1,
            command=SolverCommand.SEARCH,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["https://example.com/fedora"])],
            ),
            search_args=SearchCmdArgs(packages=["bash"], latest=False),
        ),
        None,
        id="valid_search_without_latest",
    ),
    # Valid request with multiple repos
    pytest.param(
        {
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [
                    {
                        "id": "fedora",
                        "baseurl": ["https://example.com/fedora"],
                        "gpgkeys": [
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
            api_version=SolverAPIVersion.V1,
            command=SolverCommand.DUMP,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[
                    RepositoryConfig(
                        repo_id="fedora",
                        baseurl=["https://example.com/fedora"],
                        gpgkey=[
                            "https://example.com/fedora/RPM-GPG-KEY-1",
                            "https://example.com/fedora/RPM-GPG-KEY-2",
                        ],
                    ),
                    RepositoryConfig(
                        repo_id="updates",
                        metalink="https://example.com/updates/metalink",
                    ),
                ],
            ),
        ),
        None,
        id="valid_multiple_repos",
    ),
    # Valid request with gpgkey (singular) - should be converted to list
    pytest.param(
        {
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
        SolverRequest(
            api_version=SolverAPIVersion.V1,
            command=SolverCommand.DUMP,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[
                    RepositoryConfig(
                        repo_id="fedora",
                        baseurl=["https://example.com/fedora"],
                        gpgkey=["https://example.com/fedora/RPM-GPG-KEY"],
                    ),
                ],
            ),
        ),
        None,
        id="valid_gpgkey_singular",
    ),
    # Valid request with both gpgkey and gpgkeys - should merge
    pytest.param(
        {
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [
                    {
                        "id": "fedora",
                        "baseurl": ["https://example.com/fedora"],
                        "gpgkey": "https://example.com/fedora/RPM-GPG-KEY-1",
                        "gpgkeys": ["https://example.com/fedora/RPM-GPG-KEY-2"],
                    },
                ],
            },
        },
        SolverRequest(
            api_version=SolverAPIVersion.V1,
            command=SolverCommand.DUMP,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[
                    RepositoryConfig(
                        repo_id="fedora",
                        baseurl=["https://example.com/fedora"],
                        gpgkey=[
                            "https://example.com/fedora/RPM-GPG-KEY-1",
                            "https://example.com/fedora/RPM-GPG-KEY-2",
                        ],
                    ),
                ],
            ),
        ),
        None,
        id="valid_gpgkey_and_gpgkeys_merge",
    ),
    # Valid request with sslverify default (True)
    pytest.param(
        {
            "command": "dump",
            "arch": "x86_64",
            "releasever": "43",
            "cachedir": "/tmp/cache",
            "arguments": {
                "repos": [{"id": "fedora", "baseurl": ["https://example.com/fedora"]}],
            },
        },
        SolverRequest(
            api_version=SolverAPIVersion.V1,
            command=SolverCommand.DUMP,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["https://example.com/fedora"])],
            ),
        ),
        None,
        id="valid_sslverify_default",
    ),
    # Valid request with optional-metadata
    pytest.param(
        {
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
            api_version=SolverAPIVersion.V1,
            command=SolverCommand.DUMP,
            config=SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["https://example.com/fedora"])],
                optional_metadata=["filelists", "other"],
            ),
        ),
        None,
        id="valid_with_optional_metadata",
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
    # Invalid: search not a dict
    pytest.param(
        {
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
])
@pytest.mark.parametrize("parser", [
    parse_request_v1,
    parse_request,
], ids=["parse_request_v1", "parse_request"])
def test_parse_request_v1(request_dict, expected_result, expected_error, parser):
    """Test parse_request function with various valid and invalid inputs"""
    if expected_error:
        with pytest.raises(InvalidRequestError, match=expected_error):
            parser(request_dict)
    else:
        result = parser(request_dict)
        assert_object_equal(result, expected_result)
