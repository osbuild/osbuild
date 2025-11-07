import pytest

testutil_dnf4 = pytest.importorskip("osbuild.testutil.dnf4")


def test_depsolve_pkgset(repo_servers):
    pkgset = testutil_dnf4.depsolve_pkgset(repo_servers, ["bash"])
    assert len(pkgset) == 15
    assert "bash" in [pkg.name for pkg in pkgset]
