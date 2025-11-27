"""
Test the depsolve() method of the DNF solver implementations (DNF4 and DNF5).
"""

import os

import pytest

from osbuild.solver.request import DepsolveCmdArgs, DepsolveTransaction, RepositoryConfig, SolverConfig


def _get_dnf4_solver_class():
    dnf4_solver_module = pytest.importorskip("osbuild.solver.dnf")
    return dnf4_solver_module.DNF


def _get_dnf5_solver_class():
    dnf5_solver_module = pytest.importorskip("osbuild.solver.dnf5")
    return dnf5_solver_module.DNF5


def _instantiate_solver(solver_class, cachedir, persistdir, repo_servers):
    """Prepare a solver object for testing."""
    repo_configs = [RepositoryConfig(repo_id=r["name"], baseurl=[r["address"]]) for r in repo_servers]
    solver = solver_class(
        config=SolverConfig(
            arch="x86_64",
            releasever="9",
            module_platform_id="platform:el9",
            cachedir=os.fspath(cachedir),
            repos=repo_configs,
        ),
        persistdir=os.fspath(persistdir),
    )
    return solver


@pytest.mark.parametrize("solver", [
    pytest.param(_get_dnf4_solver_class(), id="dnf4"),
    pytest.param(_get_dnf5_solver_class(), id="dnf5"),
])
def test_results_sorted(tmp_path, repo_servers, solver):
    cachedir = tmp_path / "cache"
    persistdir = tmp_path / "persist"
    solver = _instantiate_solver(solver, cachedir, persistdir, repo_servers)

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
