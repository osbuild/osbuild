"""
Test the depsolve() method of the DNF solver implementations (DNF4 and DNF5).
"""

import pytest

from osbuild.solver.request import DepsolveCmdArgs, DepsolveTransaction

from .conftest import instantiate_solver


def _get_dnf4_solver_class():
    dnf4_solver_module = pytest.importorskip("osbuild.solver.dnf")
    return dnf4_solver_module.DNF


def _get_dnf5_solver_class():
    dnf5_solver_module = pytest.importorskip("osbuild.solver.dnf5")
    return dnf5_solver_module.DNF5


@pytest.mark.parametrize("solver", [
    pytest.param(_get_dnf4_solver_class(), id="dnf4"),
    pytest.param(_get_dnf5_solver_class(), id="dnf5"),
])
def test_results_sorted(tmp_path, repo_servers, solver):
    cachedir = tmp_path / "cache"
    persistdir = tmp_path / "persist"
    solver = instantiate_solver(solver, cachedir, persistdir, repo_servers)

    depsolve_args = DepsolveCmdArgs(
        transactions=[
            DepsolveTransaction(
                package_specs=["bash"],
            )
        ]
    )
    depsolve_result = solver.depsolve(depsolve_args)
    assert depsolve_result.packages == sorted(depsolve_result.packages)
    assert depsolve_result.repositories == sorted(depsolve_result.repositories, key=lambda x: x.repo_id)
