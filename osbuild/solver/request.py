"""
Request model for the solver API

This module contains data classes representing solver requests and their
components. These models are populated from API request dicts by version-
specific parsers in the api/ module.
"""

from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from osbuild.solver.exceptions import InvalidRequestError
from osbuild.solver.model import Repository

if TYPE_CHECKING:
    from osbuild.solver.api import SolverAPIVersion


class SolverCommand(Enum):
    """Supported solver commands"""
    DEPSOLVE = "depsolve"
    DUMP = "dump"
    SEARCH = "search"

    def __str__(self) -> str:
        return self.value


class DepsolveTransaction:
    """A single transaction for dependency resolution"""

    def __init__(
        self,
        package_specs: List[str],
        exclude_specs: Optional[List[str]] = None,
        repo_ids: Optional[List[str]] = None,
        module_enable_specs: Optional[List[str]] = None,
        install_weak_deps: bool = False,
    ):
        # pylint: disable=fixme
        # XXX: We can't enforce this, because there is a "bug" in the osbuild/images "os" pipeline implementation.
        # https://github.com/osbuild/images/commit/8b779619aa0c3a9b8537f6bb79324303cb87909c introduced three
        # transactions, but the "customizations" package set is added to the "chain" unconditionally, even if it
        # is empty. This is the case for "container" and "wsl" image types. Other image types enable at least
        # SELinux, which adds the "selinux-policy-targeted" package to the list.
        # if not package_specs:
        #     raise InvalidRequestError("Depsolve transaction must contain at least one package specification")

        self.package_specs = package_specs
        self.exclude_specs = exclude_specs
        self.repo_ids = repo_ids
        self.module_enable_specs = module_enable_specs
        self.install_weak_deps = install_weak_deps

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DepsolveTransaction):
            return False
        return (
            self.package_specs == other.package_specs
            and self.exclude_specs == other.exclude_specs
            and self.repo_ids == other.repo_ids
            and self.module_enable_specs == other.module_enable_specs
            and self.install_weak_deps == other.install_weak_deps
        )

    def __hash__(self) -> int:
        return hash((
            tuple(self.package_specs),
            tuple(self.exclude_specs) if self.exclude_specs else None,
            tuple(self.repo_ids) if self.repo_ids else None,
            tuple(self.module_enable_specs) if self.module_enable_specs else None,
            self.install_weak_deps,
        ))

    def __repr__(self) -> str:
        return f"DepsolveTransaction(package_specs={self.package_specs}, exclude_specs={self.exclude_specs}, " \
            f"repo_ids={self.repo_ids}, module_enable_specs={self.module_enable_specs}, " \
            f"install_weak_deps={self.install_weak_deps})"


class SBOMRequest:
    """
    SBOM generation request

    XXX: this will be deprecated once the SBOM generation is moved to osbuild/images
    """

    def __init__(self, sbom_type: str):
        if not sbom_type:
            raise InvalidRequestError("SBOM type cannot be empty")
        if sbom_type != "spdx":
            raise InvalidRequestError(f"Unsupported SBOM type '{sbom_type}'. Supported types: spdx")
        self.sbom_type = sbom_type

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SBOMRequest):
            return False
        return self.sbom_type == other.sbom_type

    def __hash__(self) -> int:
        return hash(self.sbom_type)


class DepsolveCmdArgs:
    """Arguments for the DEPSOLVE command"""

    def __init__(self, transactions: List[DepsolveTransaction], sbom_request: Optional[SBOMRequest] = None):
        if not transactions:
            raise InvalidRequestError("Depsolve command must contain at least one transaction")

        self.transactions = transactions
        self.sbom_request = sbom_request

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DepsolveCmdArgs):
            return False
        return self.transactions == other.transactions and self.sbom_request == other.sbom_request

    def __hash__(self) -> int:
        return hash(
            (
                tuple(self.transactions),
                self.sbom_request,
            )
        )

    def __repr__(self) -> str:
        return f"DepsolveCmdArgs(transactions={self.transactions}, sbom_request={self.sbom_request})"


class SearchCmdArgs:
    """Arguments for the SEARCH command"""

    def __init__(self, packages: List[str], latest: bool = False):
        self.packages = packages
        self.latest = latest

        if not packages:
            raise InvalidRequestError("Search command must contain at least one package specification")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SearchCmdArgs):
            return False
        return self.packages == other.packages and self.latest == other.latest

    def __hash__(self) -> int:
        return hash((tuple(self.packages), self.latest))


class SolverConfig:
    """Solver configuration"""

    def __init__(
        self,
        arch: str,
        releasever: str,
        cachedir: str,
        module_platform_id: Optional[str] = None,
        proxy: Optional[str] = None,
        repos: Optional[List[Repository]] = None,
        root_dir: Optional[str] = None,
        optional_metadata: Optional[List[str]] = None,
    ):
        self.arch = arch
        self.releasever = releasever
        self.cachedir = cachedir
        self.module_platform_id = module_platform_id
        self.proxy = proxy
        self.repos = repos
        self.root_dir = root_dir
        self.optional_metadata = optional_metadata

        # Validation
        required_args = ["arch", "releasever", "cachedir"]
        for arg in required_args:
            if not getattr(self, arg):
                raise InvalidRequestError(f"Field '{arg}' is required")

        # Repository validation
        if not repos and not root_dir:
            raise InvalidRequestError("No 'repos' or 'root_dir' specified")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SolverConfig):
            return False
        return (
            self.arch == other.arch
            and self.releasever == other.releasever
            and self.cachedir == other.cachedir
            and self.module_platform_id == other.module_platform_id
            and self.proxy == other.proxy
            and self.repos == other.repos
            and self.root_dir == other.root_dir
            and self.optional_metadata == other.optional_metadata
        )

    def __hash__(self) -> int:
        return hash((
            self.arch,
            self.releasever,
            self.cachedir,
            self.module_platform_id,
            self.proxy,
            tuple(self.repos) if self.repos else None,
            self.root_dir,
            tuple(self.optional_metadata) if self.optional_metadata else None,
        ))

    def __repr__(self) -> str:
        return f"SolverConfig(arch={self.arch}, releasever={self.releasever}, cachedir={self.cachedir}, " \
            f"module_platform_id={self.module_platform_id}, proxy={self.proxy}, repos={self.repos}, " \
            f"root_dir={self.root_dir}, optional_metadata={self.optional_metadata})"


# pylint: disable=too-many-instance-attributes
class SolverRequest:
    """Version-agnostic solver request"""

    def __init__(
        self,
        api_version: "SolverAPIVersion",
        command: SolverCommand,
        config: SolverConfig,
        # Command-specific args
        depsolve_args: Optional[DepsolveCmdArgs] = None,
        search_args: Optional[SearchCmdArgs] = None,
    ):
        self.api_version = api_version
        self.command = command
        self.config = config
        self.search_args = search_args
        self.depsolve_args = depsolve_args

        if not command:
            raise InvalidRequestError("Field 'command' is required")

        if command not in [SolverCommand.DEPSOLVE, SolverCommand.SEARCH, SolverCommand.DUMP]:
            raise InvalidRequestError(
                f"Invalid command '{command}': must be one of {', '.join([c.value for c in SolverCommand])}")

        # Command-specific validation
        if command != SolverCommand.DEPSOLVE and depsolve_args:
            raise InvalidRequestError("Depsolve arguments are only supported with 'depsolve' command")

        if command != SolverCommand.SEARCH and search_args:
            raise InvalidRequestError("Search arguments are only supported with 'search' command")

        if command == SolverCommand.DEPSOLVE and not depsolve_args:
            raise InvalidRequestError("Depsolve command requires arguments")

        if command == SolverCommand.SEARCH and not search_args:
            raise InvalidRequestError("Search command requires arguments")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SolverRequest):
            return False
        return (
            self.api_version == other.api_version
            and self.command == other.command
            and self.config == other.config
            and self.depsolve_args == other.depsolve_args
            and self.search_args == other.search_args
        )

    def __hash__(self) -> int:
        return hash((
            self.api_version,
            self.command,
            self.config,
            self.depsolve_args,
            self.search_args,
        ))

    def __repr__(self) -> str:
        return f"SolverRequest(api_version={self.api_version}, command={self.command}, config={self.config}, " \
            f"depsolve_args={self.depsolve_args}, search_args={self.search_args})"
