from datetime import datetime

import pytest

testutil_dnf4 = pytest.importorskip("osbuild.testutil.dnf4")
sbom_dnf = pytest.importorskip("osbuild.util.sbom.dnf")


def test_dnf_pkgset_to_sbom_pkgset(repo_servers):
    dnf_pkgset = testutil_dnf4.depsolve_pkgset(repo_servers, ["bash"])
    bom_pkgset = sbom_dnf.dnf_pkgset_to_sbom_pkgset(dnf_pkgset)
    assert len(bom_pkgset) == len(dnf_pkgset)
    for bom_pkg, dnf_pkg in zip(bom_pkgset, dnf_pkgset):
        assert bom_pkg.name == dnf_pkg.name
        assert bom_pkg.version == dnf_pkg.version
        assert bom_pkg.release == dnf_pkg.release
        assert bom_pkg.architecture == dnf_pkg.arch
        assert bom_pkg.epoch == dnf_pkg.epoch
        assert bom_pkg.license_declared == dnf_pkg.license
        assert bom_pkg.vendor == dnf_pkg.vendor
        assert bom_pkg.build_date == datetime.fromtimestamp(dnf_pkg.buildtime)
        assert bom_pkg.summary == dnf_pkg.summary
        assert bom_pkg.description == dnf_pkg.description
        assert bom_pkg.source_rpm == dnf_pkg.sourcerpm
        assert bom_pkg.homepage == dnf_pkg.url

        assert bom_pkg.checksums == {
            sbom_dnf.bom_chksum_algorithm_from_hawkey(dnf_pkg.chksum[0]): dnf_pkg.chksum[1].hex()
        }

        assert bom_pkg.download_url == dnf_pkg.remote_location()
        assert bom_pkg.repository_url == dnf_pkg.remote_location()[:-len("/" + dnf_pkg.relativepath)]

        assert [dep.name for dep in bom_pkg.rpm_provides] == [dep.name for dep in dnf_pkg.provides]
        assert [dep.name for dep in bom_pkg.rpm_requires] == [dep.name for dep in dnf_pkg.requires]
        assert [dep.name for dep in bom_pkg.rpm_recommends] == [dep.name for dep in dnf_pkg.recommends]
        assert [dep.name for dep in bom_pkg.rpm_suggests] == [dep.name for dep in dnf_pkg.suggests]

    # smoke test the inter-package relationships on bash
    bash = [pkg for pkg in bom_pkgset if pkg.name == "bash"][0]
    assert len(bash.depends_on) == 3
    assert sorted(
        bash.depends_on,
        key=lambda x: x.name) == sorted(
            [pkg for pkg in bom_pkgset if pkg.name in ["filesystem", "glibc", "ncurses-libs"]],
            key=lambda x: x.name)
    assert len(bash.optional_depends_on) == 0
