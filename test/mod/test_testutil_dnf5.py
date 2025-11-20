import pytest

testutil_dnf5 = pytest.importorskip("osbuild.testutil.dnf5")


def test_depsolve_pkgset(repo_servers):
    _, pkgset = testutil_dnf5.depsolve_pkgset(repo_servers, ["bash"])
    assert len(pkgset) == 15
    assert "bash" in [pkg.get_name() for pkg in pkgset]
