import os.path

import pytest

testutil_dnf4 = pytest.importorskip("osbuild.testutil.dnf4")


def test_depsolve_pkgset():
    pkgset = testutil_dnf4.depsolve_pkgset([os.path.abspath("./test/data/testrepos/baseos")], ["bash"])
    assert len(pkgset) == 15
    assert "bash" in [pkg.name for pkg in pkgset]
