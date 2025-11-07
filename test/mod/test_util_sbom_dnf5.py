from datetime import datetime

import pytest

testutil_dnf = pytest.importorskip("osbuild.testutil.dnf5")
bom_dnf = pytest.importorskip("osbuild.util.sbom.dnf5")


def test_dnf5_pkgset_to_sbom_pkgset(repo_servers):
    _, dnf_pkgset = testutil_dnf.depsolve_pkgset(repo_servers, ["bash"])
    bom_pkgset = bom_dnf.dnf_pkgset_to_sbom_pkgset(dnf_pkgset)
    assert len(bom_pkgset) == len(dnf_pkgset)
    for bom_pkg, dnf_pkg in zip(bom_pkgset, dnf_pkgset):
        assert bom_pkg.name == dnf_pkg.get_name()
        assert bom_pkg.version == dnf_pkg.get_version()
        assert bom_pkg.release == dnf_pkg.get_release()
        assert bom_pkg.architecture == dnf_pkg.get_arch()
        assert bom_pkg.epoch == dnf_pkg.get_epoch()
        assert bom_pkg.license_declared == dnf_pkg.get_license()
        assert bom_pkg.vendor == dnf_pkg.get_vendor()
        assert bom_pkg.build_date == datetime.fromtimestamp(dnf_pkg.get_build_time())
        assert bom_pkg.summary == dnf_pkg.get_summary()
        assert bom_pkg.description == dnf_pkg.get_description()
        assert bom_pkg.source_rpm == dnf_pkg.get_sourcerpm()
        assert bom_pkg.homepage == dnf_pkg.get_url()

        dnf_pkg_checksum = dnf_pkg.get_checksum()
        if dnf_pkg_checksum:
            assert bom_pkg.checksums == {
                bom_dnf.bom_chksum_algorithm_from_libdnf5(dnf_pkg_checksum.get_type()): dnf_pkg_checksum.get_checksum()
            }

        assert bom_pkg.download_url == dnf_pkg.get_remote_locations()[0]
        assert bom_pkg.repository_url == dnf_pkg.get_remote_locations()[0][:-len("/" + dnf_pkg.get_location())]

        assert [dep.name for dep in bom_pkg.rpm_provides] == [dep.get_name() for dep in dnf_pkg.get_provides()]
        assert [dep.name for dep in bom_pkg.rpm_requires] == [dep.get_name() for dep in dnf_pkg.get_requires()]
        assert [dep.name for dep in bom_pkg.rpm_recommends] == [dep.get_name() for dep in dnf_pkg.get_recommends()]
        assert [dep.name for dep in bom_pkg.rpm_suggests] == [dep.get_name() for dep in dnf_pkg.get_suggests()]

    # smoke test the inter-package relationships on bash
    bash = [pkg for pkg in bom_pkgset if pkg.name == "bash"][0]
    assert len(bash.depends_on) == 3
    assert sorted(
        bash.depends_on,
        key=lambda x: x.name) == sorted(
            [pkg for pkg in bom_pkgset if pkg.name in ["filesystem", "glibc", "ncurses-libs"]],
            key=lambda x: x.name)
    assert len(bash.optional_depends_on) == 0
