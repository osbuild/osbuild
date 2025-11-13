import importlib
from enum import Enum
from types import ModuleType
from typing import Any, Dict, List, Optional

from osbuild.solver import InvalidRequestError
from osbuild.solver.model import Package, Repository
from osbuild.solver.request import SolverRequest


class SolverAPIVersion(Enum):
    V1 = 1

    def __str__(self) -> str:
        return self.name.lower()


def get_api_module(api_version: SolverAPIVersion) -> ModuleType:
    try:
        return importlib.import_module(f"osbuild.solver.api.v{api_version.value}")
    except ImportError as e:
        raise ValueError(f"Invalid solver API version: {api_version}") from e


def parse_request(request_dict: Dict) -> SolverRequest:
    """
    Parse a request dict into a SolverRequest object

    Detects API version from the request (defaults to V1) and
    uses the appropriate version-specific parser.
    """
    # Get API version from the request, default to V1, because the current (V1)
    # API implementation does not set any version field.
    # pylint: disable=fixme
    # XXX: remove the default and make it an error once V1 is deprecated.
    version_num = request_dict.get("api_version", 1)
    try:
        api_version = SolverAPIVersion(version_num)
    except ValueError as e:
        raise InvalidRequestError(f"Invalid API version: {e}") from e

    api_module = get_api_module(api_version)
    return api_module.parse_request(request_dict)


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
