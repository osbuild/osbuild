import importlib
from enum import Enum
from types import ModuleType
from typing import Any, Dict, List, Optional

from osbuild.solver.model import Package, Repository


class SolverAPIVersion(Enum):
    V1 = 1

    def __str__(self) -> str:
        return self.name.lower()


def get_api_module(api_version: SolverAPIVersion) -> ModuleType:
    try:
        return importlib.import_module(f"osbuild.solver.api.v{api_version.value}")
    except ImportError as e:
        raise ValueError(f"Invalid solver API version: {api_version}") from e


def serialize_response_depsolve(
    api_version: SolverAPIVersion,
    solver: str,
    packages: List[Package],
    repositories: List[Repository],
    modules: Optional[dict] = None,
    sbom: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Serializes a Solver API response for the DEPSOLVE command.
    """
    api_module = get_api_module(api_version)
    return api_module.serialize_response_depsolve(solver, packages, repositories, modules, sbom)


def serialize_response_dump(api_version: SolverAPIVersion, packages: List[Package]) -> List[Dict[str, Any]]:
    """
    Serializes a Solver API response for the DUMP command.
    """
    api_module = get_api_module(api_version)
    return api_module.serialize_response_dump(packages)


def serialize_response_search(api_version: SolverAPIVersion, packages: List[Package]) -> List[Dict[str, Any]]:
    """
    Serializes a Solver API response for the SEARCH command.
    """
    api_module = get_api_module(api_version)
    return api_module.serialize_response_search(packages)
