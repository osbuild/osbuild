"""Common fixtures and utilities"""

import os

from osbuild.solver.model import Repository
from osbuild.solver.request import SolverConfig


def assert_object_equal(obj1, obj2):
    """
    Assert that two objects are equal.

    If the objects are not equal, print the differences.
    """
    assert isinstance(obj1, type(obj2)), f"Objects are not of the same type: {type(obj1)} != {type(obj2)}"
    if obj1 != obj2:
        differences = []
        all_keys = set(vars(obj1).keys()) | set(vars(obj2).keys())
        for key in sorted(all_keys):
            val1 = vars(obj1).get(key)
            val2 = vars(obj2).get(key)
            if val1 != val2:
                differences.append(f"  {key}:")
                differences.append(f"    OBJ1: {val1!r}")
                differences.append(f"    OBJ2: {val2!r}")
        assert False, "Objects are not equal:\n" + "\n".join(differences)


def instantiate_solver(solver_class, cachedir, persistdir, repo_servers):
    """Prepare a solver object for testing."""
    repo_configs = [Repository.from_request(repo_id=r["name"], baseurl=[r["address"]]) for r in repo_servers]
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
