# pylint: disable=fixme
# XXX: remove 'Provides: osbuild-dnf-json-api = 8' from the osbuild.spec file when this file is removed

from typing import Any, Dict, List

from osbuild.solver.exceptions import InvalidRequestError
from osbuild.solver.model import DepsolveResult, DumpResult, Package, Repository, SearchResult
from osbuild.solver.request import (
    DepsolveCmdArgs,
    DepsolveTransaction,
    RepositoryConfig,
    SBOMRequest,
    SearchCmdArgs,
    SolverCommand,
    SolverConfig,
    SolverRequest,
)


def _package_as_dict_dump_search(package: Package) -> dict:
    """
    Returns a dictionary representation of the RPM package for the DUMP and SEARCH commands.
    """
    return {
        "name": package.name,
        "summary": package.summary,
        "description": package.description,
        "url": package.url,
        "repo_id": package.repo_id,
        "epoch": package.epoch,
        "version": package.version,
        "release": package.release,
        "arch": package.arch,
        "buildtime": package.build_time_as_rfc3339(),
        "license": package.license,
    }


def _package_as_dict_depsolve(package: Package) -> dict:
    """
    Returns a dictionary representation of the RPM package for the DEPSOLVE command.
    """
    return {
        "name": package.name,
        "epoch": package.epoch,
        "version": package.version,
        "release": package.release,
        "arch": package.arch,
        "repo_id": package.repo_id,
        "path": package.location,
        "remote_location": package.remote_locations[0],
        "checksum": str(package.checksum),
    }


def _repository_as_dict(repository: Repository) -> dict:
    """
    Returns a dictionary representation of the repository. In v1, it is used only by the DEPSOLVE command.
    """
    return {
        "id": repository.repo_id,
        "name": repository.name,
        "baseurl": repository.baseurl,
        "metalink": repository.metalink,
        "mirrorlist": repository.mirrorlist,
        "gpgcheck": repository.gpgcheck,
        "repo_gpgcheck": repository.repo_gpgcheck,
        "gpgkeys": repository.gpgkeys,
        "sslverify": repository.sslverify,
        "sslcacert": repository.sslcacert,
        "sslclientkey": repository.sslclientkey,
        "sslclientcert": repository.sslclientcert,
    }


# pylint: disable=unused-argument
def serialize_response_dump(solver: str, result: DumpResult) -> List[dict]:
    return [_package_as_dict_dump_search(package) for package in result.packages]


# pylint: disable=unused-argument
def serialize_response_search(solver: str, result: SearchResult) -> List[dict]:
    return [_package_as_dict_dump_search(package) for package in result.packages]


def serialize_response_depsolve(solver: str, result: DepsolveResult) -> Dict[str, Any]:
    last_transaction = result.transactions[-1] if result.transactions else []
    d = {
        "solver": solver,
        "packages": [_package_as_dict_depsolve(package) for package in last_transaction],
        "repos": {repository.repo_id: _repository_as_dict(repository) for repository in result.repositories},
        "modules": result.modules if result.modules else {},
    }

    if result.sbom:
        d["sbom"] = result.sbom

    return d


# pylint: disable=too-many-branches
def _parse_repository(repo_dict: Dict[str, Any]) -> RepositoryConfig:
    """
    Parse repository config from dict

    Note: Merges 'gpgkey' (singular) and 'gpgkeys' (plural) fields for backward compatibility.
    """

    if not isinstance(repo_dict, dict):
        raise TypeError("Repository config must be a dict")

    gpgkeys = []
    # NB: 'gpgkey' is no longer used by osbuild/images implementation, remove it in the next API version.
    if "gpgkey" in repo_dict:
        gpgkeys.append(repo_dict["gpgkey"])
    if "gpgkeys" in repo_dict:
        gpgkeys.extend(repo_dict["gpgkeys"])

    kwargs = {
        "repo_id": repo_dict["id"],
    }
    if "name" in repo_dict:
        kwargs["name"] = repo_dict["name"]
    if "baseurl" in repo_dict:
        baseurl_value = repo_dict["baseurl"]
        if not isinstance(baseurl_value, list):
            raise TypeError(f"'baseurl' must be a list of URLs, got {type(baseurl_value).__name__}")
        kwargs["baseurl"] = baseurl_value
    if "metalink" in repo_dict:
        kwargs["metalink"] = repo_dict["metalink"]
    if "mirrorlist" in repo_dict:
        kwargs["mirrorlist"] = repo_dict["mirrorlist"]
    if "gpgcheck" in repo_dict:
        kwargs["gpgcheck"] = repo_dict["gpgcheck"]
    if "repo_gpgcheck" in repo_dict:
        kwargs["repo_gpgcheck"] = repo_dict["repo_gpgcheck"]
    if gpgkeys:
        kwargs["gpgkey"] = gpgkeys
    if "sslverify" in repo_dict:
        kwargs["sslverify"] = repo_dict["sslverify"]
    if "sslcacert" in repo_dict:
        kwargs["sslcacert"] = repo_dict["sslcacert"]
    if "sslclientkey" in repo_dict:
        kwargs["sslclientkey"] = repo_dict["sslclientkey"]
    if "sslclientcert" in repo_dict:
        kwargs["sslclientcert"] = repo_dict["sslclientcert"]
    if "metadata_expire" in repo_dict:
        kwargs["metadata_expire"] = repo_dict["metadata_expire"]
    if "module_hotfixes" in repo_dict:
        kwargs["module_hotfixes"] = repo_dict["module_hotfixes"]

    return RepositoryConfig(**kwargs)


def _parse_depsolve_transaction(trans_dict: Dict[str, Any]) -> DepsolveTransaction:
    """Parse a transaction from a dict"""

    if not isinstance(trans_dict, dict):
        raise TypeError("Depsolve transaction must be a dict")

    kwargs = {
        "package_specs": trans_dict.get("package-specs", []),
    }
    if "exclude-specs" in trans_dict:
        kwargs["exclude_specs"] = trans_dict["exclude-specs"]
    if "repo-ids" in trans_dict:
        kwargs["repo_ids"] = trans_dict["repo-ids"]
    if "module-enable-specs" in trans_dict:
        kwargs["module_enable_specs"] = trans_dict["module-enable-specs"]
    if "install_weak_deps" in trans_dict:
        kwargs["install_weak_deps"] = trans_dict["install_weak_deps"]

    return DepsolveTransaction(**kwargs)


# pylint: disable=too-many-branches, too-many-statements
def parse_request(request_dict: Dict[str, Any]) -> SolverRequest:
    """Parse a V1 request dict into a SolverRequest object"""
    # Import here to avoid circular dependency at module level
    # pylint: disable=import-outside-toplevel
    from . import SolverAPIVersion

    # Get required top-level fields
    try:
        command_str = request_dict["command"]
        arch = request_dict["arch"]
        releasever = request_dict["releasever"]
        cachedir = request_dict["cachedir"]
        arguments = request_dict["arguments"]
    except KeyError as e:
        raise InvalidRequestError(f"Missing required field {e}") from e

    # Validate and parse command
    try:
        command = SolverCommand(command_str)
    except ValueError as e:
        valid_cmds = ", ".join([c.value for c in SolverCommand])
        raise InvalidRequestError(
            f"Invalid command '{command_str}': must be one of {valid_cmds}"
        ) from e

    # Get optional top-level fields
    module_platform_id = request_dict.get("module_platform_id")
    proxy = request_dict.get("proxy")

    # Validate and parse command arguments
    if not isinstance(arguments, dict):
        raise InvalidRequestError("Field 'arguments' must be a dict")

    repos = None
    if "repos" in arguments:
        if not isinstance(arguments["repos"], list):
            raise InvalidRequestError("Field 'repos' must be a list")
        try:
            repos = [_parse_repository(r) for r in arguments["repos"]]
        except (ValueError, TypeError) as e:
            raise InvalidRequestError(f"Invalid repository config: {e}") from e
        except KeyError as e:
            raise InvalidRequestError(f"Missing required field {e} in 'repos' item configuration") from e

    root_dir = arguments.get("root_dir")
    optional_metadata = arguments.get("optional-metadata")

    if optional_metadata and not isinstance(optional_metadata, list):
        raise InvalidRequestError("Field 'optional-metadata' must be a list")

    depsolve_transactions = []
    if command == SolverCommand.DEPSOLVE and "transactions" in arguments:
        if not isinstance(arguments["transactions"], list):
            raise InvalidRequestError("Field 'transactions' must be a list")
        try:
            depsolve_transactions = [_parse_depsolve_transaction(t) for t in arguments["transactions"]]
        except (ValueError, TypeError) as e:
            raise InvalidRequestError(f"Invalid depsolve transaction: {e}") from e
        except KeyError as e:
            raise InvalidRequestError(f"Missing required field {e} in 'transactions' list") from e

    search_args = None
    if command == SolverCommand.SEARCH and "search" in arguments:
        if not isinstance(arguments["search"], dict):
            raise InvalidRequestError("Field 'search' must be a dict")
        try:
            packages = arguments["search"]["packages"]
            if not isinstance(packages, list):
                raise InvalidRequestError("Field 'packages' must be a list")
            latest = arguments["search"].get("latest", False)
            search_args = SearchCmdArgs(packages, latest)
        except (ValueError, TypeError) as e:
            raise InvalidRequestError(f"Invalid search arguments: {e}") from e
        except KeyError as e:
            raise InvalidRequestError(f"Missing required field {e} in 'search' dict") from e

    sbom_request = None
    if "sbom" in arguments:
        if not isinstance(arguments["sbom"], dict):
            raise InvalidRequestError("Field 'sbom' must be a dict")
        try:
            sbom_request = SBOMRequest(arguments["sbom"]["type"])
        except (ValueError, TypeError) as e:
            raise InvalidRequestError(f"Invalid value for 'type' in 'sbom': {e}") from e
        except KeyError as e:
            raise InvalidRequestError("Missing required field 'type' in 'sbom'") from e
        if command != SolverCommand.DEPSOLVE:
            raise InvalidRequestError("Field 'sbom' is only supported with 'depsolve' command")

    depsolve_args = None
    if depsolve_transactions:
        depsolve_args = DepsolveCmdArgs(
            transactions=depsolve_transactions,
            sbom_request=sbom_request,
        )

    return SolverRequest(
        api_version=SolverAPIVersion.V1,
        command=command,
        config=SolverConfig(
            arch=arch,
            releasever=releasever,
            cachedir=cachedir,
            module_platform_id=module_platform_id,
            proxy=proxy,
            repos=repos,
            root_dir=root_dir,
            optional_metadata=optional_metadata,
        ),
        depsolve_args=depsolve_args,
        search_args=search_args,
    )
