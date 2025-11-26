import abc
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from osbuild.solver.api import serialize_response_depsolve, serialize_response_dump, serialize_response_search
from osbuild.solver.exceptions import GPGKeyReadError
from osbuild.solver.model import DepsolveResult, DumpResult, SearchResult
from osbuild.solver.request import DepsolveCmdArgs, SearchCmdArgs, SolverRequest


class Solver(abc.ABC):
    @abc.abstractmethod
    def dump(self) -> DumpResult:
        pass

    @abc.abstractmethod
    def depsolve(self, args: DepsolveCmdArgs) -> DepsolveResult:
        pass

    @abc.abstractmethod
    def search(self, args: SearchCmdArgs) -> SearchResult:
        pass


class SolverBase(Solver):
    # put any shared helpers in here

    # Override this in the subclass
    SOLVER_NAME = "unknown"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.SOLVER_NAME == SolverBase.SOLVER_NAME:
            raise ValueError(f"{cls.__name__} must override SOLVER_NAME")

    def __init__(
        self,
        request: "SolverRequest",
        persistdir: os.PathLike,
        license_index_path: Optional[os.PathLike] = None,
    ):
        self.request = request
        self.persistdir = persistdir
        self.license_index_path = license_index_path

    def serialize_response_depsolve(self, result: DepsolveResult) -> Dict[str, Any]:
        """Transform a DepsolveResult to a JSON-serializable response."""
        return serialize_response_depsolve(self.request.api_version, self.SOLVER_NAME, result)

    def serialize_response_dump(self, result: DumpResult) -> List[Dict[str, Any]]:
        """Transform a DumpResult to a JSON-serializable response."""
        return serialize_response_dump(self.request.api_version, self.SOLVER_NAME, result)

    def serialize_response_search(self, result: SearchResult) -> List[Dict[str, Any]]:
        """Transform a SearchResult to a JSON-serializable response."""
        return serialize_response_search(self.request.api_version, self.SOLVER_NAME, result)


def modify_rootdir_path(path, root_dir):
    if path and root_dir:
        # if the root_dir is set, we need to translate the key path to be under this directory
        return os.path.join(root_dir, path.lstrip("/"))
    return path


def read_keys(paths, root_dir=None):
    keys = []
    for path in paths:
        url = urllib.parse.urlparse(path)
        if url.scheme == "file":
            path = url.path
            path = modify_rootdir_path(path, root_dir)
            try:
                with open(path, mode="r", encoding="utf-8") as keyfile:
                    keys.append(keyfile.read())
            except Exception as e:
                raise GPGKeyReadError(f"error loading gpg key from {path}: {e}") from e
        elif url.scheme in ["http", "https"]:
            try:
                resp = urllib.request.urlopen(urllib.request.Request(path))
                keys.append(resp.read().decode())
            except urllib.error.URLError as e:
                raise GPGKeyReadError(f"error reading remote gpg key at {path}: {e}") from e
        else:
            raise GPGKeyReadError(f"unknown url scheme for gpg key: {url.scheme} ({path})")
    return keys
