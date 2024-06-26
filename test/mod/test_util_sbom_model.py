import pytest

from osbuild.util.sbom.model import RPMPackage


def test_rpmpackage_uuid():
    pkg_a = RPMPackage("PackageA", "1.0.0", "1.fc40", "x86_64")
    pkg_a_duplicate = RPMPackage("PackageA", "1.0.0", "1.fc40", "x86_64")

    pkg_a_v2 = RPMPackage("PackageA", "2.0.0", "1.fc40", "x86_64")
    pkg_a_fc41 = RPMPackage("PackageA", "1.0.0", "1.fc41", "x86_64")
    pkg_a_aarch64 = RPMPackage("PackageA", "1.0.0", "1.fc40", "aarch64")

    pkg_b = RPMPackage("PackageB", "1.0.0", "1.fc40", "x86_64")

    assert pkg_a.uuid() == pkg_a_duplicate.uuid()
    for pkg in [pkg_a_v2, pkg_a_fc41, pkg_a_aarch64, pkg_b]:
        assert pkg_a.uuid() != pkg.uuid()


@pytest.mark.parametrize("package,purl", (
    (
        RPMPackage("PackageA", "1.0.0", "1.fc40", "x86_64"),
        "pkg:rpm/PackageA@1.0.0-1.fc40?arch=x86_64"
    ),
    (
        RPMPackage("PackageA", "1.0.0", "1.fc40", "x86_64", epoch=123),
        "pkg:rpm/PackageA@1.0.0-1.fc40?arch=x86_64&epoch=123"
    ),
    (
        RPMPackage("PackageA", "1.0.0", "1.fc40", "x86_64", vendor="Fedora Project"),
        "pkg:rpm/fedora%20project/PackageA@1.0.0-1.fc40?arch=x86_64"
    ),
    (
        RPMPackage("PackageA", "1.0.0", "1.el9", "x86_64", vendor="CentOS"),
        "pkg:rpm/centos/PackageA@1.0.0-1.el9?arch=x86_64"
    ),
    (
        RPMPackage("PackageA", "1.0.0", "1.el9", "x86_64", vendor="Red Hat, Inc."),
        "pkg:rpm/red%20hat%2C%20inc./PackageA@1.0.0-1.el9?arch=x86_64"
    ),
    (
        RPMPackage("PackageA", "1.0.0", "1.fc40", "x86_64", vendor="Fedora Project", repository_url="https://example.org/repo/"),
        "pkg:rpm/fedora%20project/PackageA@1.0.0-1.fc40?arch=x86_64&repository_url=https://example.org/repo/"
    ),

))
def test_rpmpackage_purl(package, purl):
    assert package.purl() == purl
