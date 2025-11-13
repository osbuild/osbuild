# pylint: disable=too-many-lines
"""
Unit tests for osbuild.solver.request classes
"""

import pytest

from osbuild.solver.api import SolverAPIVersion
from osbuild.solver.exceptions import InvalidRequestError
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


class TestDepsolveTransaction:
    """Tests for the DepsolveTransaction class"""

    @pytest.mark.parametrize("kwargs,exception", [
        pytest.param(
            {"package_specs": ["bash", "vim"]},
            None,
            id="minimal_transaction",
        ),
        pytest.param(
            {
                "package_specs": ["bash", "vim"],
                "exclude_specs": ["emacs"],
                "repo_ids": ["fedora", "updates"],
                "module_enable_specs": ["nodejs:18"],
                "install_weak_deps": True,
            },
            None,
            id="full_transaction",
        ),
        # Invalid requests
        pytest.param(
            {"package_specs": []},
            InvalidRequestError("Depsolve transaction must contain at least one package specification"),
            id="invalid_empty_package_specs",
        ),
    ])
    def test_constructor(self, kwargs, exception):
        if exception:
            with pytest.raises(type(exception), match=str(exception)):
                DepsolveTransaction(**kwargs)
        else:
            txn = DepsolveTransaction(**kwargs)
            assert txn.package_specs == kwargs.get("package_specs")
            assert txn.exclude_specs == kwargs.get("exclude_specs")
            assert txn.repo_ids == kwargs.get("repo_ids")
            assert txn.module_enable_specs == kwargs.get("module_enable_specs")
            assert txn.install_weak_deps == kwargs.get("install_weak_deps", False)

    @pytest.mark.parametrize("txn1,txn2,expected", [
        pytest.param(
            DepsolveTransaction(package_specs=["bash", "vim"]),
            DepsolveTransaction(package_specs=["bash", "vim"]),
            True,
            id="same_minimal",
        ),
        pytest.param(
            DepsolveTransaction(package_specs=["bash"]),
            DepsolveTransaction(package_specs=["vim"]),
            False,
            id="different_package_specs",
        ),
        pytest.param(
            DepsolveTransaction(package_specs=["bash"], exclude_specs=["emacs"]),
            DepsolveTransaction(package_specs=["bash"], exclude_specs=["vim"]),
            False,
            id="different_exclude_specs",
        ),
        pytest.param(
            DepsolveTransaction(package_specs=["bash"], repo_ids=["fedora"]),
            DepsolveTransaction(package_specs=["bash"], repo_ids=["updates"]),
            False,
            id="different_repo_ids",
        ),
        pytest.param(
            DepsolveTransaction(package_specs=["bash"], module_enable_specs=["nodejs:18"]),
            DepsolveTransaction(package_specs=["bash"], module_enable_specs=["nodejs:20"]),
            False,
            id="different_module_enable_specs",
        ),
        pytest.param(
            DepsolveTransaction(package_specs=["bash"], install_weak_deps=True),
            DepsolveTransaction(package_specs=["bash"], install_weak_deps=False),
            False,
            id="different_install_weak_deps",
        ),
        pytest.param(
            DepsolveTransaction(
                package_specs=["bash", "vim"],
                exclude_specs=["emacs"],
                repo_ids=["fedora", "updates"],
                module_enable_specs=["nodejs:18"],
                install_weak_deps=True,
            ),
            DepsolveTransaction(
                package_specs=["bash", "vim"],
                exclude_specs=["emacs"],
                repo_ids=["fedora", "updates"],
                module_enable_specs=["nodejs:18"],
                install_weak_deps=True,
            ),
            True,
            id="complex_attributes_same",
        ),
        pytest.param(
            DepsolveTransaction(
                package_specs=["bash", "vim"],
                exclude_specs=["emacs"],
                repo_ids=["fedora", "updates"],
                module_enable_specs=["nodejs:18"],
                install_weak_deps=True,
            ),
            DepsolveTransaction(
                package_specs=["bash", "vim"],
                exclude_specs=["emacs"],
                repo_ids=["fedora", "updates"],
                module_enable_specs=["nodejs:20"],
                install_weak_deps=True,
            ),
            False,
            id="complex_attributes_different",
        ),
    ])
    def test_equality(self, txn1, txn2, expected):
        assert (txn1 == txn2) == expected
        if expected:
            assert hash(txn1) == hash(txn2)

    def test_collections(self):
        txn1 = DepsolveTransaction(package_specs=["bash"])
        txn2 = DepsolveTransaction(package_specs=["bash"])
        txn3 = DepsolveTransaction(package_specs=["vim"])
        assert len({txn1, txn2, txn3}) == 2
        txn_dict = {txn1: "v1"}
        txn_dict[txn2] = "v2"
        assert len(txn_dict) == 1 and txn_dict[txn1] == "v2"


class TestSBOMRequest:
    """Tests for the SBOMRequest class"""

    @pytest.mark.parametrize("sbom_type,exception", [
        pytest.param(
            "spdx",
            None,
            id="valid_spdx_type",
        ),
        # Invalid requests
        pytest.param(
            "cyclonedx",
            InvalidRequestError("Unsupported SBOM type 'cyclonedx'"),
            id="invalid_cyclonedx_type",
        ),
        pytest.param(
            "",
            InvalidRequestError("SBOM type cannot be empty"),
            id="invalid_empty_sbom_type",
        ),
    ])
    def test_constructor(self, sbom_type, exception):
        if exception:
            with pytest.raises(type(exception), match=str(exception)):
                SBOMRequest(sbom_type)
        else:
            sbom = SBOMRequest(sbom_type)
            assert sbom.sbom_type == sbom_type

    @pytest.mark.parametrize("sbom1,sbom2,expected", [
        pytest.param(
            SBOMRequest(sbom_type="spdx"),
            SBOMRequest(sbom_type="spdx"),
            True,
            id="same_type",
        ),
    ])
    def test_equality(self, sbom1, sbom2, expected):
        assert (sbom1 == sbom2) == expected
        if expected:
            assert hash(sbom1) == hash(sbom2)

    def test_collections(self):
        sbom1 = SBOMRequest(sbom_type="spdx")
        sbom2 = SBOMRequest(sbom_type="spdx")
        assert len({sbom1, sbom2}) == 1
        sbom_dict = {sbom1: "v1"}
        sbom_dict[sbom2] = "v2"
        assert len(sbom_dict) == 1 and sbom_dict[sbom1] == "v2"


class TestDepsolveCmdArgs:
    """Tests for the DepsolveCmdArgs class"""

    @pytest.mark.parametrize("kwargs,exception", [
        pytest.param(
            {"transactions": [DepsolveTransaction(package_specs=["bash"])]},
            None,
            id="minimal_transactions",
        ),
        pytest.param(
            {"transactions": [DepsolveTransaction(package_specs=["bash"]), DepsolveTransaction(package_specs=["vim"])]},
            None,
            id="multiple_transactions",
        ),
        pytest.param(
            {
                "transactions": [DepsolveTransaction(package_specs=["bash"])],
                "sbom_request": SBOMRequest("spdx"),
            },
            None,
            id="with_sbom_request",
        ),
        # Invalid requests
        pytest.param(
            {"transactions": []},
            InvalidRequestError("Depsolve command must contain at least one transaction"),
            id="invalid_empty_transactions",
        ),
    ])
    def test_constructor(self, kwargs, exception):
        if exception:
            with pytest.raises(type(exception), match=str(exception)):
                DepsolveCmdArgs(**kwargs)
        else:
            args = DepsolveCmdArgs(**kwargs)
            assert len(args.transactions) == len(kwargs["transactions"])
            assert args.sbom_request == kwargs.get("sbom_request")

    @pytest.mark.parametrize("args1,args2,expected", [
        pytest.param(
            DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
            DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
            True,
            id="same_single_transaction",
        ),
        pytest.param(
            DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
            DepsolveCmdArgs([DepsolveTransaction(package_specs=["vim"])]),
            False,
            id="different_transactions",
        ),
        pytest.param(
            DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
            DepsolveCmdArgs([
                DepsolveTransaction(package_specs=["bash"]),
                DepsolveTransaction(package_specs=["vim"]),
            ]),
            False,
            id="different_transaction_count",
        ),
        pytest.param(
            DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])], SBOMRequest("spdx")),
            DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
            False,
            id="different_sbom_request",
        ),
    ])
    def test_equality(self, args1, args2, expected):
        assert (args1 == args2) == expected
        if expected:
            assert hash(args1) == hash(args2)

    def test_collections(self):
        args1 = DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])])
        args2 = DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])])
        args3 = DepsolveCmdArgs([DepsolveTransaction(package_specs=["vim"])])
        assert len({args1, args2, args3}) == 2
        args_dict = {args1: "v1"}
        args_dict[args2] = "v2"
        assert len(args_dict) == 1 and args_dict[args1] == "v2"


class TestSearchCmdArgs:
    """Tests for the SearchCmdArgs class"""

    @pytest.mark.parametrize("packages,latest,exception", [
        pytest.param(
            ["bash", "vim"],
            False,
            None,
            id="minimal_packages",
        ),
        pytest.param(
            ["bash", "vim"],
            True,
            None,
            id="with_latest",
        ),
        # Invalid requests
        pytest.param(
            [],
            False,
            InvalidRequestError("Search command must contain at least one package specification"),
            id="invalid_empty_packages",
        ),
    ])
    def test_constructor(self, packages, latest, exception):
        if exception:
            with pytest.raises(type(exception), match=str(exception)):
                SearchCmdArgs(packages, latest)
        else:
            args = SearchCmdArgs(packages, latest)
            assert args.packages == packages
            assert args.latest is latest

    @pytest.mark.parametrize("args1,args2,expected", [
        pytest.param(
            SearchCmdArgs(packages=["bash"]),
            SearchCmdArgs(packages=["bash"]),
            True,
            id="same_packages",
        ),
        pytest.param(
            SearchCmdArgs(packages=["bash"]),
            SearchCmdArgs(packages=["vim"]),
            False,
            id="different_packages",
        ),
        pytest.param(
            SearchCmdArgs(packages=["bash"], latest=True),
            SearchCmdArgs(packages=["bash"], latest=False),
            False,
            id="different_latest",
        ),
    ])
    def test_equality(self, args1, args2, expected):
        assert (args1 == args2) == expected
        if expected:
            assert hash(args1) == hash(args2)

    def test_collections(self):
        args1 = SearchCmdArgs(packages=["bash", "vim"], latest=True)
        args2 = SearchCmdArgs(packages=["bash", "vim"], latest=True)
        args3 = SearchCmdArgs(packages=["gcc"], latest=False)
        assert len({args1, args2, args3}) == 2
        args_dict = {args1: "v1"}
        args_dict[args2] = "v2"
        assert len(args_dict) == 1 and args_dict[args1] == "v2"


class TestRepositoryConfig:
    """Tests for the RepositoryConfig class"""

    @pytest.mark.parametrize("kwargs,exception", [
        pytest.param(
            {"repo_id": "fedora", "baseurl": ["http://example.com"]},
            None,
            id="minimal_with_baseurl",
        ),
        pytest.param(
            {"repo_id": "fedora", "metalink": "http://example.com/metalink"},
            None,
            id="minimal_with_metalink",
        ),
        pytest.param(
            {"repo_id": "fedora", "mirrorlist": "http://example.com/mirrorlist"},
            None,
            id="minimal_with_mirrorlist",
        ),
        pytest.param(
            {
                "repo_id": "fedora",
                "baseurl": ["http://example.com/fedora"],
                "name": "Fedora 43",
                "gpgcheck": True,
                "repo_gpgcheck": True,
                "gpgkey": ["http://example.com/key.asc"],
                "sslverify": True,
                "sslcacert": "/etc/pki/ca.pem",
                "sslclientkey": "/etc/pki/client.key",
                "sslclientcert": "/etc/pki/client.cert",
                "metadata_expire": "1h",
                "module_hotfixes": True
            },
            None,
            id="full_config",
        ),
        # Invalid requests
        pytest.param(
            {"repo_id": ""},
            InvalidRequestError("Repository 'id' cannot be empty"),
            id="invalid_empty_repo_id",
        ),
        pytest.param(
            {"repo_id": "fedora"},
            InvalidRequestError("At least one of 'baseurl', 'metalink', or 'mirrorlist' must be specified"),
            id="invalid_missing_url_fields",
        ),
    ])
    def test_constructor(self, kwargs, exception):
        if exception:
            with pytest.raises(type(exception), match=str(exception)):
                RepositoryConfig(**kwargs)
        else:
            repo = RepositoryConfig(**kwargs)
            assert repo.repo_id == kwargs.get("repo_id")
            assert repo.name == kwargs.get("name")
            assert repo.baseurl == kwargs.get("baseurl")
            assert repo.metalink == kwargs.get("metalink")
            assert repo.mirrorlist == kwargs.get("mirrorlist")
            assert repo.gpgcheck == kwargs.get("gpgcheck")
            assert repo.repo_gpgcheck == kwargs.get("repo_gpgcheck")
            assert repo.gpgkey == kwargs.get("gpgkey")
            assert repo.sslverify == kwargs.get("sslverify", True)
            assert repo.sslcacert == kwargs.get("sslcacert")
            assert repo.sslclientkey == kwargs.get("sslclientkey")
            assert repo.sslclientcert == kwargs.get("sslclientcert")
            assert repo.metadata_expire == kwargs.get("metadata_expire", "20s")
            assert repo.module_hotfixes == kwargs.get("module_hotfixes")

    @pytest.mark.parametrize("repo1,repo2,expected", [
        # Basic fields
        pytest.param(
            RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"]),
            RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"]),
            True,
            id="same_minimal",
        ),
        pytest.param(
            RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"]),
            RepositoryConfig(repo_id="updates", baseurl=["http://example.com"]),
            False,
            id="different_repo_id",
        ),
        pytest.param(
            RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"]),
            RepositoryConfig(repo_id="fedora", baseurl=["http://other.com"]),
            False,
            id="different_baseurl",
        ),
        pytest.param(
            RepositoryConfig(repo_id="fedora", metalink="http://example.com/metalink"),
            RepositoryConfig(repo_id="fedora", mirrorlist="http://example.com/mirrorlist"),
            False,
            id="different_url_type",
        ),
        # Boolean and optional fields
        pytest.param(
            RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"], gpgcheck=True),
            RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"], gpgcheck=False),
            False,
            id="different_gpgcheck",
        ),
        pytest.param(
            RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"], gpgkey=["http://example.com/key1.asc"]),
            RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"], gpgkey=["http://example.com/key2.asc"]),
            False,
            id="different_gpgkey",
        ),
        pytest.param(
            RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"], metadata_expire="1h"),
            RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"], metadata_expire="2h"),
            False,
            id="different_metadata_expire",
        ),
        # Complex combination
        pytest.param(
            RepositoryConfig(
                repo_id="fedora",
                baseurl=["http://example.com"],
                gpgcheck=True,
                gpgkey=["http://example.com/key1.asc"],
                sslverify=True,
                sslcacert="/etc/pki/ca.pem",
                sslclientkey="/etc/pki/client.key",
                sslclientcert="/etc/pki/client.cert",
                metadata_expire="1h",
                module_hotfixes=True,
            ),
            RepositoryConfig(
                repo_id="fedora",
                baseurl=["http://example.com"],
                gpgcheck=True,
                gpgkey=["http://example.com/key1.asc"],
                sslverify=True,
                sslcacert="/etc/pki/ca.pem",
                sslclientkey="/etc/pki/client.key",
                sslclientcert="/etc/pki/client.cert",
                metadata_expire="1h",
                module_hotfixes=True,
            ),
            True,
            id="complex_attributes_same",
        ),
        pytest.param(
            RepositoryConfig(
                repo_id="fedora",
                baseurl=["http://example.com"],
                gpgcheck=True,
                gpgkey=["http://example.com/key1.asc"],
                metadata_expire="1h",
                module_hotfixes=True,
            ),
            RepositoryConfig(
                repo_id="fedora",
                baseurl=["http://example.com"],
                gpgcheck=True,
                gpgkey=["http://example.com/key1.asc"],
                sslverify=True,
                sslcacert="/etc/pki/ca.pem",
                sslclientkey="/etc/pki/client.key",
                sslclientcert="/etc/pki/client.cert",
                metadata_expire="2h",
                module_hotfixes=True,
            ),
            False,
            id="complex_attributes_different",
        ),
    ])
    def test_equality(self, repo1, repo2, expected):
        assert (repo1 == repo2) == expected
        if expected:
            assert hash(repo1) == hash(repo2)

    def test_collections(self):
        repo1 = RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])
        repo2 = RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])
        repo3 = RepositoryConfig(repo_id="updates", baseurl=["http://example.com"])
        assert len({repo1, repo2, repo3}) == 2
        repo_dict = {repo1: "v1"}
        repo_dict[repo2] = "v2"
        assert len(repo_dict) == 1 and repo_dict[repo1] == "v2"


class TestSolverConfig:
    """Tests for the SolverConfig class"""

    @pytest.mark.parametrize("kwargs,exception", [
        pytest.param(
            {
                "arch": "x86_64",
                "releasever": "43",
                "cachedir": "/tmp/cache",
                "repos": [RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
            },
            None,
            id="minimal_with_repos",
        ),
        pytest.param(
            {
                "arch": "x86_64",
                "releasever": "43",
                "cachedir": "/tmp/cache",
                "root_dir": "/mnt/sysroot",
            },
            None,
            id="minimal_with_root_dir",
        ),
        pytest.param(
            {
                "arch": "x86_64",
                "releasever": "43",
                "cachedir": "/tmp/cache",
                "repos": [
                    RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"]),
                    RepositoryConfig(repo_id="updates", baseurl=["http://example.com/updates"]),
                ],
                "optional_metadata": ["filelists", "other"],
                "module_platform_id": "platform:f43",
                "proxy": "http://proxy.example.com:8080",
            },
            None,
            id="full_config",
        ),
        # Invalid requests
        pytest.param(
            {
                "arch": "",
                "releasever": "43",
                "cachedir": "/tmp/cache",
                "repos": [RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
            },
            InvalidRequestError("Field 'arch' is required"),
            id="invalid_empty_arch",
        ),
        pytest.param(
            {
                "arch": "x86_64",
                "releasever": "",
                "cachedir": "/tmp/cache",
                "repos": [RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
            },
            InvalidRequestError("Field 'releasever' is required"),
            id="invalid_empty_releasever",
        ),
        pytest.param(
            {
                "arch": "x86_64",
                "releasever": "43",
                "cachedir": "",
                "repos": [RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
            },
            InvalidRequestError("Field 'cachedir' is required"),
            id="invalid_empty_cachedir",
        ),
        pytest.param(
            {
                "arch": "x86_64",
                "releasever": "43",
                "cachedir": "/tmp/cache",
            },
            InvalidRequestError("No 'repos' or 'root_dir' specified"),
            id="invalid_missing_repos_and_root_dir",
        ),
    ])
    def test_constructor(self, kwargs, exception):
        if exception:
            with pytest.raises(type(exception), match=str(exception)):
                SolverConfig(**kwargs)
        else:
            config = SolverConfig(**kwargs)
            assert config.arch == kwargs.get("arch")
            assert config.releasever == kwargs.get("releasever")
            assert config.cachedir == kwargs.get("cachedir")
            assert config.repos == kwargs.get("repos")
            assert config.root_dir == kwargs.get("root_dir")
            assert config.optional_metadata == kwargs.get("optional_metadata")
            assert config.module_platform_id == kwargs.get("module_platform_id")
            assert config.proxy == kwargs.get("proxy")

    @pytest.mark.parametrize("config1,config2,expected", [
        # Basic fields
        pytest.param(
            SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
            ),
            SolverConfig(
                arch="x86_64",
                releasever="43",
                cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
            ),
            True,
            id="same_minimal",
        ),
        pytest.param(
            SolverConfig(
                arch="x86_64", releasever="43", cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
            ),
            SolverConfig(
                arch="aarch64", releasever="43", cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
            ),
            False,
            id="different_arch",
        ),
        pytest.param(
            SolverConfig(
                arch="x86_64", releasever="43", cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])]
            ),
            SolverConfig(
                arch="x86_64", releasever="44", cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
            ),
            False,
            id="different_releasever",
        ),
        pytest.param(
            SolverConfig(
                arch="x86_64", releasever="43", cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
            ),
            SolverConfig(
                arch="x86_64", releasever="43", cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="updates", baseurl=["http://example.com"])],
            ),
            False,
            id="different_repos",
        ),
        # Optional fields
        pytest.param(
            SolverConfig(
                arch="x86_64", releasever="43", cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                module_platform_id="platform:f43",
            ),
            SolverConfig(
                arch="x86_64", releasever="43", cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                module_platform_id="platform:f44",
            ),
            False,
            id="different_module_platform_id",
        ),
        pytest.param(
            SolverConfig(
                arch="x86_64", releasever="43", cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                proxy="http://proxy1.example.com:8080",
            ),
            SolverConfig(
                arch="x86_64", releasever="43", cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                proxy="http://proxy2.example.com:8080",
            ),
            False,
            id="different_proxy",
        ),
        pytest.param(
            SolverConfig(arch="x86_64", releasever="43", cachedir="/tmp/cache", root_dir="/mnt/sysroot"),
            SolverConfig(arch="x86_64", releasever="43", cachedir="/tmp/cache", root_dir="/mnt/other"),
            False,
            id="different_root_dir",
        ),
        pytest.param(
            SolverConfig(
                arch="x86_64", releasever="43", cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                optional_metadata=["filelists"],
            ),
            SolverConfig(
                arch="x86_64", releasever="43", cachedir="/tmp/cache",
                repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                optional_metadata=["other"],
            ),
            False,
            id="different_optional_metadata",
        ),
    ])
    def test_equality(self, config1, config2, expected):
        assert (config1 == config2) == expected
        if expected:
            assert hash(config1) == hash(config2)

    def test_collections(self):
        config1 = SolverConfig(
            arch="x86_64",
            releasever="43",
            cachedir="/tmp/cache",
            repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
        )
        config2 = SolverConfig(
            arch="x86_64",
            releasever="43",
            cachedir="/tmp/cache",
            repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
        )
        config3 = SolverConfig(
            arch="aarch64",
            releasever="43",
            cachedir="/tmp/cache",
            repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
        )
        assert len({config1, config2, config3}) == 2
        config_dict = {config1: "v1"}
        config_dict[config2] = "v2"
        assert len(config_dict) == 1 and config_dict[config1] == "v2"


class TestSolverRequest:
    """Tests for the SolverRequest class"""

    @pytest.mark.parametrize("kwargs,exception", [
        pytest.param(
            {
                "api_version": SolverAPIVersion.V1,
                "command": SolverCommand.DEPSOLVE,
                "config": SolverConfig(
                    arch="x86_64",
                    releasever="43",
                    cachedir="/tmp/cache",
                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                ),
                "depsolve_args": DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
            },
            None,
            id="minimal_depsolve",
        ),
        pytest.param(
            {
                "api_version": SolverAPIVersion.V1,
                "command": SolverCommand.DUMP,
                "config": SolverConfig(
                    arch="x86_64",
                    releasever="43",
                    cachedir="/tmp/cache",
                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                ),
            },
            None,
            id="minimal_dump",
        ),
        pytest.param(
            {
                "api_version": SolverAPIVersion.V1,
                "command": SolverCommand.SEARCH,
                "config": SolverConfig(
                    arch="x86_64",
                    releasever="43",
                    cachedir="/tmp/cache",
                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                ),
                "search_args": SearchCmdArgs(packages=["bash"]),
            },
            None,
            id="minimal_search",
        ),
        pytest.param(
            {
                "api_version": SolverAPIVersion.V1,
                "command": SolverCommand.DEPSOLVE,
                "config": SolverConfig(
                    arch="x86_64",
                    releasever="43",
                    cachedir="/tmp/cache",
                    root_dir="/mnt/sysroot",
                ),
                "depsolve_args": DepsolveCmdArgs([DepsolveTransaction(
                    package_specs=["bash"],
                    exclude_specs=["emacs"],
                    repo_ids=["fedora", "updates"],
                    module_enable_specs=["nodejs:18"],
                    install_weak_deps=True,
                )]),
            },
            None,
            id="with_root_dir",
        ),
        pytest.param(
            {
                "api_version": SolverAPIVersion.V1,
                "command": SolverCommand.DEPSOLVE,
                "config": SolverConfig(
                    arch="x86_64",
                    releasever="43",
                    cachedir="/tmp/cache",
                    repos=[
                        RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"]),
                        RepositoryConfig(repo_id="updates", baseurl=["http://example.com/updates"]),
                    ],
                    optional_metadata=["filelists", "other"],
                    module_platform_id="platform:f43",
                    proxy="http://proxy.example.com:8080",
                ),
                "depsolve_args": DepsolveCmdArgs(
                    transactions=[DepsolveTransaction(
                        package_specs=["bash"],
                        exclude_specs=["emacs"],
                        repo_ids=["fedora", "updates"],
                        module_enable_specs=["nodejs:18"],
                        install_weak_deps=True,
                    )],
                    sbom_request=SBOMRequest(sbom_type="spdx"),
                ),
            },
            None,
            id="depsolve_full_config",
        ),
        # Invalid requests
        pytest.param(
            {
                "api_version": SolverAPIVersion.V1,
                "command": SolverCommand.DEPSOLVE,
                "config": SolverConfig(
                    arch="x86_64",
                    releasever="43",
                    cachedir="/tmp/cache",
                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                ),
            },
            InvalidRequestError("Depsolve command requires arguments"),
            id="invalid_missing_depsolve_args",
        ),
        pytest.param(
            {
                "api_version": SolverAPIVersion.V1,
                "command": SolverCommand.SEARCH,
                "config": SolverConfig(
                    arch="x86_64",
                    releasever="43",
                    cachedir="/tmp/cache",
                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                ),
            },
            InvalidRequestError("Search command requires arguments"),
            id="invalid_missing_search_args",
        ),
        pytest.param(
            {
                "api_version": SolverAPIVersion.V1,
                "command": SolverCommand.SEARCH,
                "config": SolverConfig(
                    arch="x86_64",
                    releasever="43",
                    cachedir="/tmp/cache",
                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                ),
                "depsolve_args": DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
            },
            InvalidRequestError("Depsolve arguments are only supported with 'depsolve' command"),
            id="invalid_depsolve_args_with_search_command",
        ),
        pytest.param(
            {
                "api_version": SolverAPIVersion.V1,
                "command": SolverCommand.DUMP,
                "config": SolverConfig(
                    arch="x86_64",
                    releasever="43",
                    cachedir="/tmp/cache",
                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                ),
                "depsolve_args": DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
            },
            InvalidRequestError("Depsolve arguments are only supported with 'depsolve' command"),
            id="invalid_depsolve_args_with_dump_command",
        ),
        pytest.param(
            {
                "api_version": SolverAPIVersion.V1,
                "command": SolverCommand.DEPSOLVE,
                "config": SolverConfig(
                    arch="x86_64",
                    releasever="43",
                    cachedir="/tmp/cache",
                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                ),
                "search_args": SearchCmdArgs(packages=["bash"]),
            },
            InvalidRequestError("Search arguments are only supported with 'search' command"),
            id="invalid_search_args_with_depsolve_command",
        ),
        pytest.param(
            {
                "api_version": SolverAPIVersion.V1,
                "command": SolverCommand.DUMP,
                "config": SolverConfig(
                    arch="x86_64",
                    releasever="43",
                    cachedir="/tmp/cache",
                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                ),
                "search_args": SearchCmdArgs(packages=["bash"]),
            },
            InvalidRequestError("Search arguments are only supported with 'search' command"),
            id="invalid_search_args_with_dump_command",
        ),
        pytest.param(
            {
                "api_version": SolverAPIVersion.V1,
                "command": "invalid_command",
                "config": SolverConfig(
                    arch="x86_64",
                    releasever="43",
                    cachedir="/tmp/cache",
                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                ),
            },
            InvalidRequestError("Invalid command 'invalid_command': must be one of depsolve, dump, search"),
            id="invalid_command",
        ),
        pytest.param(
            {
                "api_version": SolverAPIVersion.V1,
                "command": "",
                "config": SolverConfig(
                    arch="x86_64",
                    releasever="43",
                    cachedir="/tmp/cache",
                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])],
                ),
            },
            InvalidRequestError("Field 'command' is required"),
            id="invalid_empty_command",
        ),
    ])
    def test_constructor(self, kwargs, exception):
        if exception:
            with pytest.raises(type(exception), match=str(exception)):
                SolverRequest(**kwargs)
        else:
            request = SolverRequest(**kwargs)
            assert request.api_version == kwargs.get("api_version")
            assert request.command == kwargs.get("command")
            assert request.config == kwargs.get("config")
            assert request.depsolve_args == kwargs.get("depsolve_args")
            assert request.search_args == kwargs.get("search_args")

    @pytest.mark.parametrize("req1,req2,expected", [
        # Basic fields
        pytest.param(
            SolverRequest(
                api_version=SolverAPIVersion.V1,
                command=SolverCommand.DEPSOLVE,
                config=SolverConfig(arch="x86_64", releasever="43", cachedir="/tmp/cache",
                                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])]),
                depsolve_args=DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
            ),
            SolverRequest(
                api_version=SolverAPIVersion.V1,
                command=SolverCommand.DEPSOLVE,
                config=SolverConfig(arch="x86_64", releasever="43", cachedir="/tmp/cache",
                                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])]),
                depsolve_args=DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
            ),
            True,
            id="same_depsolve",
        ),
        pytest.param(
            SolverRequest(
                api_version=SolverAPIVersion.V1,
                command=SolverCommand.SEARCH,
                config=SolverConfig(arch="x86_64", releasever="43", cachedir="/tmp/cache",
                                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])]),
                search_args=SearchCmdArgs(packages=["bash"]),
            ),
            SolverRequest(
                api_version=SolverAPIVersion.V1,
                command=SolverCommand.SEARCH,
                config=SolverConfig(arch="x86_64", releasever="43", cachedir="/tmp/cache",
                                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])]),
                search_args=SearchCmdArgs(packages=["bash"]),
            ),
            True,
            id="same_search",
        ),
        pytest.param(
            SolverRequest(
                api_version=SolverAPIVersion.V1,
                command=SolverCommand.DEPSOLVE,
                config=SolverConfig(arch="x86_64", releasever="43", cachedir="/tmp/cache",
                                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])]),
                depsolve_args=DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
            ),
            SolverRequest(
                api_version=SolverAPIVersion.V1,
                command=SolverCommand.SEARCH,
                config=SolverConfig(arch="x86_64", releasever="43", cachedir="/tmp/cache",
                                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])]),
                search_args=SearchCmdArgs(packages=["bash"]),
            ),
            False,
            id="different_command",
        ),
        pytest.param(
            SolverRequest(
                api_version=SolverAPIVersion.V1,
                command=SolverCommand.DEPSOLVE,
                config=SolverConfig(arch="x86_64", releasever="43", cachedir="/tmp/cache",
                                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])]),
                depsolve_args=DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
            ),
            SolverRequest(
                api_version=SolverAPIVersion.V1,
                command=SolverCommand.DEPSOLVE,
                config=SolverConfig(arch="aarch64", releasever="43", cachedir="/tmp/cache",
                                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])]),
                depsolve_args=DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
            ),
            False,
            id="different_config",
        ),
        pytest.param(
            SolverRequest(
                api_version=SolverAPIVersion.V1,
                command=SolverCommand.DEPSOLVE,
                config=SolverConfig(arch="x86_64", releasever="43", cachedir="/tmp/cache",
                                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])]),
                depsolve_args=DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
            ),
            SolverRequest(
                api_version=SolverAPIVersion.V1,
                command=SolverCommand.DEPSOLVE,
                config=SolverConfig(arch="x86_64", releasever="43", cachedir="/tmp/cache",
                                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])]),
                depsolve_args=DepsolveCmdArgs([DepsolveTransaction(package_specs=["vim"])]),
            ),
            False,
            id="different_depsolve_args",
        ),
        pytest.param(
            SolverRequest(
                api_version=SolverAPIVersion.V1,
                command=SolverCommand.SEARCH,
                config=SolverConfig(arch="x86_64", releasever="43", cachedir="/tmp/cache",
                                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])]),
                search_args=SearchCmdArgs(packages=["bash"]),
            ),
            SolverRequest(
                api_version=SolverAPIVersion.V1,
                command=SolverCommand.SEARCH,
                config=SolverConfig(arch="x86_64", releasever="43", cachedir="/tmp/cache",
                                    repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])]),
                search_args=SearchCmdArgs(packages=["vim"]),
            ),
            False,
            id="different_search_args",
        ),
    ])
    def test_equality(self, req1, req2, expected):
        assert (req1 == req2) == expected
        if expected:
            assert hash(req1) == hash(req2)

    def test_collections(self):
        req1 = SolverRequest(
            api_version=SolverAPIVersion.V1,
            command=SolverCommand.DEPSOLVE,
            config=SolverConfig(arch="x86_64", releasever="43", cachedir="/tmp/cache",
                                repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])]),
            depsolve_args=DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
        )
        req2 = SolverRequest(
            api_version=SolverAPIVersion.V1,
            command=SolverCommand.DEPSOLVE,
            config=SolverConfig(arch="x86_64", releasever="43", cachedir="/tmp/cache",
                                repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])]),
            depsolve_args=DepsolveCmdArgs([DepsolveTransaction(package_specs=["bash"])]),
        )
        req3 = SolverRequest(
            api_version=SolverAPIVersion.V1,
            command=SolverCommand.SEARCH,
            config=SolverConfig(arch="x86_64", releasever="43", cachedir="/tmp/cache",
                                repos=[RepositoryConfig(repo_id="fedora", baseurl=["http://example.com"])]),
            search_args=SearchCmdArgs(packages=["bash"]),
        )
        assert len({req1, req2, req3}) == 2
        req_dict = {req1: "v1"}
        req_dict[req2] = "v2"
        assert len(req_dict) == 1 and req_dict[req1] == "v2"
