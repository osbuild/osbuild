"""
Test the depsolve() method of the DNF solver implementations (DNF4 and DNF5).
"""

import pytest

from osbuild.solver.exceptions import DepsolveError
from osbuild.solver.request import DepsolveCmdArgs, DepsolveTransaction

from .conftest import instantiate_solver


def _get_dnf4_solver_class():
    dnf4_solver_module = pytest.importorskip("osbuild.solver.dnf")
    return dnf4_solver_module.DNF


def _get_dnf5_solver_class():
    dnf5_solver_module = pytest.importorskip("osbuild.solver.dnf5")
    return dnf5_solver_module.DNF5


@pytest.mark.parametrize("solver_class", [
    pytest.param(_get_dnf4_solver_class(), id="dnf4"),
    pytest.param(_get_dnf5_solver_class(), id="dnf5"),
])
def test_results_sorted(tmp_path, repo_servers, solver_class):
    cachedir = tmp_path / "cache"
    persistdir = tmp_path / "persist"
    solver = instantiate_solver(solver_class, cachedir, persistdir, repo_servers)

    depsolve_args = DepsolveCmdArgs(
        transactions=[
            DepsolveTransaction(package_specs=["bash"]),
            DepsolveTransaction(package_specs=["pkg-with-no-deps"]),
            DepsolveTransaction(package_specs=["vim"]),
        ]
    )
    depsolve_result = solver.depsolve(depsolve_args)

    assert len(depsolve_result.transactions) == len(depsolve_args.transactions)

    last_transaction_result = set()
    for transaction_result in depsolve_result.transactions:
        assert transaction_result == sorted(transaction_result)
        assert last_transaction_result.issubset(transaction_result)
        last_transaction_result = set(transaction_result)

    assert depsolve_result.repositories == sorted(depsolve_result.repositories, key=lambda x: x.repo_id)


@pytest.mark.parametrize("solver_class", [
    pytest.param(_get_dnf4_solver_class(), id="dnf4"),
    pytest.param(_get_dnf5_solver_class(), id="dnf5"),
])
def test_rhsm_flag_set_on_repositories(tmp_path, repo_servers, solver_class):
    """
    Test that repositories returned by depsolve() have the correct rhsm flag.

    This test bypasses actual RHSM secrets discovery by directly manipulating
    the solver's repo_ids_with_rhsm set after instantiation.
    """
    cachedir = tmp_path / "cache"
    persistdir = tmp_path / "persist"
    solver = instantiate_solver(solver_class, cachedir, persistdir, repo_servers)

    # Simulate that "baseos" repo was configured with rhsm=True
    # by directly setting repo_ids_with_rhsm (bypassing RHSM secrets discovery)
    solver.repo_ids_with_rhsm = {"baseos"}

    depsolve_args = DepsolveCmdArgs(
        transactions=[
            DepsolveTransaction(package_specs=["bash"]),  # baseos
            DepsolveTransaction(package_specs=["pkg-with-no-deps"]),  # custom
            DepsolveTransaction(package_specs=["vim"]),  # appstream
        ]
    )
    depsolve_result = solver.depsolve(depsolve_args)

    # Verify repositories have correct rhsm flag
    repos_by_id = {repo.repo_id: repo for repo in depsolve_result.repositories}
    assert len(repos_by_id) == 3
    assert "baseos" in repos_by_id
    for repo_id, repo in repos_by_id.items():
        expected_rhsm = repo_id == "baseos"
        assert repo.rhsm is expected_rhsm, f"Expected rhsm={expected_rhsm} for repo {repo_id}"


@pytest.mark.parametrize("solver_class", [
    pytest.param(_get_dnf4_solver_class(), id="dnf4"),
    pytest.param(
        _get_dnf5_solver_class(), id="dnf5",
        marks=pytest.mark.xfail(reason="DNF5 solver does not yet implement repo_ids restriction"),
    ),
])
def test_repoids_restricts_dependency_resolution(tmp_path, repo_servers, solver_class):
    """
    Test that repo_ids restricts not just the explicitly requested packages,
    but also their dependencies during dependency resolution.

    The 'appstream' repo contains 'vim' which has dependencies in 'baseos'.
    If only 'appstream' is allowed, the depsolve must fail because the
    dependencies from 'baseos' are not available.
    """
    cachedir = tmp_path / "cache"
    persistdir = tmp_path / "persist"
    solver = instantiate_solver(solver_class, cachedir, persistdir, repo_servers)

    # First, verify that depsolving 'vim' succeeds when both 'appstream' and
    # 'baseos' are enabled, to make sure the test package and repos are valid.
    depsolve_args_ok = DepsolveCmdArgs(
        transactions=[
            DepsolveTransaction(package_specs=["vim"], repo_ids=["appstream", "baseos"]),
        ]
    )
    result = solver.depsolve(depsolve_args_ok)
    assert len(result.transactions[0]) > 0

    # Now, restrict to only 'appstream'. The depsolve must fail because
    # vim's dependencies from 'baseos' are no longer available.
    # Both DNF4 and DNF5 are expected to raise DepsolveError here because the
    # dependency resolution fails, not just the initial package marking/selection.
    depsolve_args_fail = DepsolveCmdArgs(
        transactions=[
            DepsolveTransaction(package_specs=["vim"], repo_ids=["appstream"]),
        ]
    )
    with pytest.raises(DepsolveError, match="is filtered out by exclude filtering"):
        solver.depsolve(depsolve_args_fail)
