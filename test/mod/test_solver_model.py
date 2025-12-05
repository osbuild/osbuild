"""
Unit tests for osbuild.solver.model classes
"""

import pytest

from osbuild.solver.model import (
    Checksum,
    Dependency,
    DepsolveResult,
    DumpResult,
    Package,
    Repository,
    SearchResult,
)


class TestDependency:
    """Tests for the Dependency class"""

    @pytest.mark.parametrize("dep1,dep2,expected", [
        pytest.param(
            Dependency("glibc"), Dependency("glibc"), True, id="same_dependency"),
        pytest.param(
            Dependency("glibc", ">=", "2.34"), Dependency("glibc", ">=", "2.34"), True, id="same_dependency_full"),
        pytest.param(
            Dependency("glibc", ">=", "2.34"), Dependency("gcc", ">=", "2.34"), False, id="different_name"),
        pytest.param(
            Dependency("glibc", ">=", "2.34"), Dependency("glibc", "<=", "2.34"), False, id="different_relation"),
        pytest.param(
            Dependency("glibc", ">=", "2.34"), Dependency("glibc", ">=", "2.35"), False, id="different_version"),
    ])
    def test_equality(self, dep1, dep2, expected):
        assert (dep1 == dep2) == expected
        if expected:
            assert hash(dep1) == hash(dep2)

    def test_collections(self):
        dep1 = Dependency("glibc", ">=", "2.34")
        dep2 = Dependency("glibc", ">=", "2.34")
        dep3 = Dependency("gcc", ">=", "11")
        assert len({dep1, dep2, dep3}) == 2
        dep_dict = {dep1: "v1"}
        dep_dict[dep2] = "v2"
        assert len(dep_dict) == 1 and dep_dict[dep1] == "v2"

    def test__str__(self):
        assert str(Dependency("glibc", ">=", "2.34")) == "glibc >= 2.34"
        assert str(Dependency("glibc")) == "glibc"


class TestChecksum:
    """Tests for the Checksum class"""

    @pytest.mark.parametrize("cs1,cs2,expected", [
        pytest.param(Checksum("sha256", "abcd"), Checksum("sha256", "abcd"), True, id="same_checksum"),
        pytest.param(Checksum("sha256", "abcd"), Checksum("sha512", "abcd"), False, id="different_algorithm"),
        pytest.param(Checksum("sha256", "abcd"), Checksum("sha256", "efgh"), False, id="different_value"),
    ])
    def test_equality(self, cs1, cs2, expected):
        assert (cs1 == cs2) == expected
        if expected:
            assert hash(cs1) == hash(cs2)

    def test_collections(self):
        cs1 = Checksum("sha256", "abcd")
        cs2 = Checksum("sha256", "abcd")
        cs3 = Checksum("sha512", "efgh")
        assert len({cs1, cs2, cs3}) == 2
        cs_dict = {cs1: "v1"}
        cs_dict[cs2] = "v2"
        assert len(cs_dict) == 1 and cs_dict[cs1] == "v2"

    def test__str__(self):
        assert str(Checksum("sha256", "abcd")) == "sha256:abcd"


class TestPackage:
    """Tests for the Package class"""

    @pytest.mark.parametrize("kwargs1,kwargs2,expected", [
        # Basic fields
        pytest.param({}, {}, True, id="minimal_packages"),
        pytest.param({"epoch": 0}, {"epoch": 1}, False, id="different_epoch"),
        pytest.param({"repo_id": "fedora"}, {"repo_id": "updates"}, False, id="different_optional_field"),
        pytest.param({"license": "GPLv3+"}, {"license": "GPLv3+"}, True, id="same_optional_field"),
        # Lists
        pytest.param({"files": ["/bin/bash"]}, {"files": ["/bin/bash"]}, True, id="same_files_list"),
        pytest.param({"files": ["/bin/bash"]}, {"files": ["/bin/sh"]}, False, id="different_files_list"),
        pytest.param({"remote_locations": ["http://m1.com/bash.rpm"]},
                     {"remote_locations": ["http://m1.com/bash.rpm"]}, True, id="same_remote_locations"),
        pytest.param({"remote_locations": ["http://m1.com/bash.rpm"]}, {}, False, id="different_remote_locations"),
        # Checksums
        pytest.param({"checksum": Checksum("sha256", "abcd")},
                     {"checksum": Checksum("sha256", "abcd")}, True, id="same_checksum"),
        pytest.param({"checksum": Checksum("sha256", "abcd")},
                     {"checksum": Checksum("sha256", "efgh")}, False, id="different_checksum"),
        # Complex combination
        pytest.param({
            "requires": [Dependency("glibc", ">=", "2.34")],
            "checksum": Checksum("sha256", "abcd"),
            "files": ["/bin/bash"]
        }, {
            "requires": [Dependency("glibc", ">=", "2.34")],
            "checksum": Checksum("sha256", "abcd"),
            "files": ["/bin/bash"]
        }, True, id="complex_attributes_same"),
        pytest.param({
            "requires": [Dependency("glibc", ">=", "2.34")],
            "checksum": Checksum("sha256", "abcd"),
            "files": ["/bin/bash"]
        }, {
            "requires": [Dependency("glibc", ">=", "2.34")],
            "checksum": Checksum("sha256", "abcd"),
            "files": ["/bin/sh"]
        }, False, id="complex_attributes_different"),
    ])
    def test_equality_basic_fields(self, kwargs1, kwargs2, expected):
        pkg1 = Package("bash", "5.1", "1.fc43", "x86_64", **kwargs1)
        pkg2 = Package("bash", "5.1", "1.fc43", "x86_64", **kwargs2)
        assert (pkg1 == pkg2) == expected
        if expected:
            assert hash(pkg1) == hash(pkg2)

    def test_invalid_kwargs(self):
        with pytest.raises(ValueError, match="Package: unrecognized keyword arguments: foo"):
            Package("bash", "5.1", "1.fc43", "x86_64", foo="bar")

    def test_collections(self):
        pkg1 = Package("bash", "5.1", "1.fc43", "x86_64")
        pkg2 = Package("bash", "5.1", "1.fc43", "x86_64")
        pkg3 = Package("zsh", "5.8", "1.fc43", "x86_64")
        assert len({pkg1, pkg2, pkg3}) == 2
        pkg_dict = {pkg1: "v1"}
        pkg_dict[pkg2] = "v2"
        assert len(pkg_dict) == 1 and pkg_dict[pkg1] == "v2"

    def test__lt__(self):
        pkg1 = Package("bash", "5.1", "1.fc43", "x86_64")
        pkg2 = Package("bash", "5.8", "1.fc43", "x86_64")
        assert pkg1 < pkg2
        # Test equality case
        pkg3 = Package("bash", "5.1", "1.fc43", "x86_64")
        # pylint: disable=unnecessary-negation
        assert not pkg1 < pkg3
        # Test sorting
        assert sorted([pkg2, pkg1]) == [pkg1, pkg2]

    def test__str__(self):
        assert str(Package("bash", "5.1", "1.fc43", "x86_64", epoch=2, repo_id="fedora")) == "bash-2:5.1-1.fc43.x86_64"
        assert str(Package("bash", "5.1", "1.fc43", "x86_64")) == "bash-0:5.1-1.fc43.x86_64"

    @pytest.mark.parametrize("kwargs,expected_error", [
        pytest.param(
            {"download_size": "1024"},
            r"Package\.download_size: expected int or None, got str", id="download_size_str"
        ),
        pytest.param(
            {"provides": "glibc"},
            r"Package\.provides: expected list, got str", id="provides_str"
        ),
        pytest.param(
            {"checksum": "sha256:abc"},
            r"Package\.checksum: expected Checksum or None, got str", id="checksum_str"
        ),
        pytest.param(
            {"build_time": "12345"},
            r"Package\.build_time: expected int or None, got str", id="build_time_str"
        ),
    ])
    def test_invalid_attr_type(self, kwargs, expected_error):
        with pytest.raises(ValueError, match=expected_error):
            Package("bash", "5.1", "1.fc43", "x86_64", **kwargs)


class TestRepository:
    """Tests for the Repository class"""

    @pytest.mark.parametrize("kwargs1,kwargs2,expected", [
        # Basic fields
        pytest.param({"baseurl": ["http://example.com/r1"]},
                     {"baseurl": ["http://example.com/r1"]}, True, id="same_baseurl"),
        pytest.param({"baseurl": ["http://example.com/r1"]},
                     {"baseurl": ["http://example.com/r2"]}, False, id="different_baseurl"),
        pytest.param({"metalink": "http://example.com/meta1"},
                     {"metalink": "http://example.com/meta1"}, True, id="same_metalink"),
        pytest.param({"metalink": "http://example.com/meta1"},
                     {"metalink": "http://example.com/meta2"}, False, id="different_metalink"),
        pytest.param({"mirrorlist": "http://example.com/mirror1"},
                     {"mirrorlist": "http://example.com/mirror1"}, True, id="same_mirrorlist"),
        pytest.param({"mirrorlist": "http://example.com/mirror1"},
                     {"mirrorlist": "http://example.com/mirror2"}, False, id="different_mirrorlist"),
        # Boolean fields
        pytest.param({"baseurl": ["http://example.com/r1"], "gpgcheck": True},
                     {"baseurl": ["http://example.com/r1"], "gpgcheck": True}, True, id="same_gpgcheck"),
        pytest.param({"baseurl": ["http://example.com/r1"], "gpgcheck": True},
                     {"baseurl": ["http://example.com/r1"], "gpgcheck": False}, False, id="different_gpgcheck"),
        pytest.param({"baseurl": ["http://example.com/r1"], "repo_gpgcheck": True},
                     {"baseurl": ["http://example.com/r1"], "repo_gpgcheck": False},
                     False, id="different_repo_gpgcheck"),
        pytest.param({"baseurl": ["http://example.com/r1"], "sslverify": True},
                     {"baseurl": ["http://example.com/r1"], "sslverify": False}, False, id="different_sslverify"),
        pytest.param(
            {"baseurl": ["http://example.com/r1"], "module_hotfixes": True},
            {"baseurl": ["http://example.com/r1"], "module_hotfixes": False}, False, id="different_module_hotfixes"),
        pytest.param({"baseurl": ["http://example.com/r1"], "rhsm": True},
                     {"baseurl": ["http://example.com/r1"], "rhsm": False}, False, id="different_rhsm"),
        # SSL certificate fields
        pytest.param({"baseurl": ["http://example.com/r1"], "sslcacert": "/etc/pki/cert.pem"},
                     {"baseurl": ["http://example.com/r1"], "sslcacert": "/etc/pki/cert.pem"},
                     True, id="same_sslcacert"),
        pytest.param({"baseurl": ["http://example.com/r1"], "sslclientkey": "/etc/pki/key.pem"},
                     {"baseurl": ["http://example.com/r1"], "sslclientkey": "/etc/pki/key2.pem"},
                     False, id="different_sslclientkey"),
        # GPG keys list
        pytest.param({"baseurl": ["http://example.com/r1"], "gpgkey": ["http://example.com/key1.asc"]},
                     {"baseurl": ["http://example.com/r1"], "gpgkey": ["http://example.com/key1.asc"]},
                     True, id="same_gpgkeys"),
        pytest.param({"baseurl": ["http://example.com/r1"], "gpgkey": ["http://example.com/key1.asc"]},
                     {"baseurl": ["http://example.com/r1"], "gpgkey": ["http://example.com/key2.asc"]},
                     False, id="different_gpgkeys"),
        # Different required fields
        pytest.param({"baseurl": ["http://example.com/r1"]},
                     {"baseurl": ["http://example.com/r1"]}, True, id="minimal_repository"),
        pytest.param({"repo_id": "fedora", "baseurl": ["http://example.com/r1"]},
                     {"repo_id": "updates", "baseurl": ["http://example.com/r1"]}, False, id="different_repo_id"),
        # Complex combination
        pytest.param({
            "metalink": "http://example.com/meta1",
            "gpgcheck": True,
            "gpgkey": ["http://example.com/key1.asc"],
            "sslverify": True,
        }, {
            "metalink": "http://example.com/meta1",
            "gpgcheck": True,
            "gpgkey": ["http://example.com/key1.asc"],
            "sslverify": True,
        }, True, id="complex_attributes_same"),
        pytest.param({
            "baseurl": ["http://example.com/r1"],
            "gpgcheck": True,
            "gpgkey": ["http://example.com/key1.asc"],
        }, {
            "baseurl": ["http://example.com/r1"],
            "gpgcheck": False,
            "gpgkey": ["http://example.com/key1.asc"],
        }, False, id="complex_attributes_different"),
        pytest.param(
            {"baseurl": ["http://example.com/r1"], "metadata_expire": "1h"},
            {"baseurl": ["http://example.com/r1"], "metadata_expire": "2h"},
            False,
            id="different_metadata_expire"
        ),
    ])
    def test_equality(self, kwargs1, kwargs2, expected):
        repo1 = Repository(kwargs1.pop("repo_id", "fedora"), **kwargs1)
        repo2 = Repository(kwargs2.pop("repo_id", "fedora"), **kwargs2)
        assert (repo1 == repo2) == expected
        if expected:
            assert hash(repo1) == hash(repo2)

    def test_invalid_kwargs(self):
        with pytest.raises(ValueError, match="Repository: unrecognized keyword arguments: foo"):
            Repository("fedora", baseurl=["http://example.com/r1"], foo="bar")

    def test_missing_url_fields(self):
        with pytest.raises(
            ValueError,
            match="At least one of 'baseurl', 'metalink', or 'mirrorlist' must be specified",
        ):
            Repository("fedora")

    def test_collections(self):
        repo1 = Repository("fedora", baseurl=["http://example.com/r1"])
        repo2 = Repository("fedora", baseurl=["http://example.com/r1"])
        repo3 = Repository("updates", baseurl=["http://example.com/r2"])
        assert len({repo1, repo2, repo3}) == 2
        repo_dict = {repo1: "v1"}
        repo_dict[repo2] = "v2"
        assert len(repo_dict) == 1 and repo_dict[repo1] == "v2"

    @pytest.mark.parametrize("kwargs,expected", [
        pytest.param(
            {"repo_id": "fedora", "baseurl": ["http://example.com"]},
            "fedora", id="minimal_with_baseurl"
        ),
        pytest.param(
            {"repo_id": "fedora", "baseurl": ["http://example.com"], "name": "Fedora 43"},
            "Fedora 43", id="with_name"
        ),
    ])
    def test_name_defaults_to_repo_id(self, kwargs, expected):
        repo = Repository(**kwargs)
        assert repo.name == expected

    @pytest.mark.parametrize("kwargs,expected_attrs", [
        pytest.param(
            {"baseurl": ["http://example.com"]},
            {"sslverify": True, "metadata_expire": "20s"},
            id="defaults_applied",
        ),
        pytest.param(
            {"baseurl": ["http://example.com"], "sslverify": False, "metadata_expire": "2h"},
            {"sslverify": False, "metadata_expire": "2h"},
            id="explicit_overrides",
        ),
        pytest.param(
            {"baseurl": ["http://example.com"], "sslverify": None, "metadata_expire": None},
            {"sslverify": True, "metadata_expire": "20s"},
            id="none_values_get_defaults",
        ),
    ])
    def test_from_request(self, kwargs, expected_attrs):
        """Test that from_request() applies request-specific defaults"""
        repo = Repository.from_request(repo_id="fedora", **kwargs)
        for attr, expected_value in expected_attrs.items():
            got_attr_value = getattr(repo, attr)
            assert got_attr_value == expected_value, f"Expected {attr}={expected_value}, got {got_attr_value}"

    def test_constructor_no_defaults(self):
        """Test that regular constructor does NOT apply defaults"""
        repo = Repository("fedora", baseurl=["http://example.com"])
        assert repo.sslverify is None
        assert repo.metadata_expire is None

    @pytest.mark.parametrize("kwargs,expected_error", [
        pytest.param(
            {"gpgcheck": "yes"},
            r"Repository\.gpgcheck: expected bool or None, got str", id="gpgcheck_str"
        ),
        pytest.param(
            {"gpgcheck": 1},
            r"Repository\.gpgcheck: expected bool or None, got int", id="gpgcheck_int"
        ),
        pytest.param(
            {"gpgkey": "http://key.asc"},
            r"Repository\.gpgkey: expected list, got str", id="gpgkey_str"
        ),
        pytest.param(
            {"sslverify": "true"},
            r"Repository\.sslverify: expected bool or None, got str", id="sslverify_str"
        ),
        pytest.param(
            {"metadata_expire": 1234},
            r"Repository\.metadata_expire: expected str or None, got int", id="metadata_expire_list"
        ),
    ])
    def test_invalid_attr_type(self, kwargs, expected_error):
        with pytest.raises(ValueError, match=expected_error):
            Repository("fedora", baseurl=["http://example.com"], **kwargs)


class TestDepsolveResult:
    """Tests for the DepsolveResult class"""

    def test_equality(self):
        result1 = DepsolveResult(
            transactions=[
                [Package("bash", "5.1", "1.fc43", "x86_64")],
                [Package("zsh", "5.8", "1.fc43", "x86_64")],
            ],
            repositories=[Repository("fedora", baseurl=["http://example.com/r1"])],
            modules={"module1": {"package": {"name": "module1", "stream": "8"}, "profiles": ["base"]}},
            sbom={"sbom": "sbom document"}
        )
        result2 = DepsolveResult(
            transactions=[
                [Package("bash", "5.1", "1.fc43", "x86_64")],
                [Package("zsh", "5.8", "1.fc43", "x86_64")],
            ],
            repositories=[Repository("fedora", baseurl=["http://example.com/r1"])],
            modules={"module1": {"package": {"name": "module1", "stream": "8"}, "profiles": ["base"]}},
            sbom={"sbom": "sbom document"}
        )
        assert result1 == result2
        assert hash(result1) == hash(result2)

    def test_collections(self):
        result1 = DepsolveResult(
            transactions=[
                [Package("bash", "5.1", "1.fc43", "x86_64")],
            ],
            repositories=[Repository("fedora", baseurl=["http://example.com/r1"])]
        )
        result2 = DepsolveResult(
            transactions=[
                [Package("bash", "5.1", "1.fc43", "x86_64")],
            ],
            repositories=[Repository("fedora", baseurl=["http://example.com/r1"])]
        )
        result3 = DepsolveResult(
            transactions=[
                [Package("bash", "5.1", "1.fc43", "x86_64")],
                [Package("zsh", "5.8", "1.fc43", "x86_64")],
            ],
            repositories=[Repository("fedora", baseurl=["http://example.com/r1"])]
        )
        assert len({result1, result2, result3}) == 2
        result_dict = {result1: "v1"}
        result_dict[result2] = "v2"
        assert len(result_dict) == 1 and result_dict[result1] == "v2"


class TestDumpResult:
    """Tests for the DumpResult class"""

    def test_equality(self):
        result1 = DumpResult(
            packages=[Package("bash", "5.1", "1.fc43", "x86_64")],
            repositories=[Repository("fedora", baseurl=["http://example.com/r1"])]
        )
        result2 = DumpResult(
            packages=[Package("bash", "5.1", "1.fc43", "x86_64")],
            repositories=[Repository("fedora", baseurl=["http://example.com/r1"])]
        )
        assert result1 == result2
        assert hash(result1) == hash(result2)

    def test_collections(self):
        result1 = DumpResult(
            packages=[Package("bash", "5.1", "1.fc43", "x86_64")],
            repositories=[Repository("fedora", baseurl=["http://example.com/r1"])]
        )
        result2 = DumpResult(
            packages=[Package("bash", "5.1", "1.fc43", "x86_64")],
            repositories=[Repository("fedora", baseurl=["http://example.com/r1"])]
        )
        result3 = DumpResult(
            packages=[Package("zsh", "5.8", "1.fc43", "x86_64")],
            repositories=[Repository("fedora", baseurl=["http://example.com/r1"])]
        )
        assert len({result1, result2, result3}) == 2
        result_dict = {result1: "v1"}
        result_dict[result2] = "v2"
        assert len(result_dict) == 1 and result_dict[result1] == "v2"


class TestSearchResult:
    """Tests for the SearchResult class"""

    def test_equality(self):
        result1 = SearchResult(
            packages=[Package("bash", "5.1", "1.fc43", "x86_64")],
            repositories=[Repository("fedora", baseurl=["http://example.com/r1"])]
        )
        result2 = SearchResult(
            packages=[Package("bash", "5.1", "1.fc43", "x86_64")],
            repositories=[Repository("fedora", baseurl=["http://example.com/r1"])]
        )
        assert result1 == result2
        assert hash(result1) == hash(result2)

    def test_collections(self):
        result1 = SearchResult(
            packages=[Package("bash", "5.1", "1.fc43", "x86_64")],
            repositories=[Repository("fedora", baseurl=["http://example.com/r1"])]
        )
        result2 = SearchResult(
            packages=[Package("bash", "5.1", "1.fc43", "x86_64")],
            repositories=[Repository("fedora", baseurl=["http://example.com/r1"])]
        )
        result3 = SearchResult(
            packages=[Package("zsh", "5.8", "1.fc43", "x86_64")],
            repositories=[Repository("fedora", baseurl=["http://example.com/r1"])]
        )
        assert len({result1, result2, result3}) == 2
        result_dict = {result1: "v1"}
        result_dict[result2] = "v2"
        assert len(result_dict) == 1 and result_dict[result1] == "v2"
