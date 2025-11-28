# V2 API implementation
#
# For schema consistency, all fields are always included, even if they are not
# set or set to empty values.
#
# The only exception is the 'sbom' field, which is only included if the 'sbom'
# was explicitly requested.

from typing import Any, Dict, List, Set

from osbuild.solver.exceptions import InvalidRequestError
from osbuild.solver.model import (
    Checksum,
    Dependency,
    DepsolveResult,
    DumpResult,
    Package,
    Repository,
    SearchResult,
)
from osbuild.solver.request import (
    DepsolveCmdArgs,
    DepsolveTransaction,
    SBOMRequest,
    SearchCmdArgs,
    SolverCommand,
    SolverConfig,
    SolverRequest,
)


def _checksum_as_dict(checksum: Checksum) -> Dict[str, Any]:
    return {
        "algorithm": checksum.algorithm,
        "value": str(checksum.value),
    }


def _dependency_as_dict(dependency: Dependency) -> Dict[str, Any]:
    d = {"name": dependency.name}
    if dependency.relation:
        d["relation"] = dependency.relation
    if dependency.version:
        d["version"] = dependency.version
    return d


def _package_as_dict(package: Package) -> Dict[str, Any]:
    """
    Returns a dictionary representation of the RPM package.

    All fields are always included for schema consistency.
    Scalar fields may be None, list fields are empty arrays if not set.
    """
    return {
        # Core fields (always expected to have values)
        "name": package.name,
        "epoch": package.epoch,
        "version": package.version,
        "release": package.release,
        "arch": package.arch,
        "repo_id": package.repo_id,
        "location": package.location,
        "remote_locations": package.remote_locations,
        "checksum": _checksum_as_dict(package.checksum) if package.checksum else None,

        # Metadata fields (may be None)
        "header_checksum": _checksum_as_dict(package.header_checksum) if package.header_checksum else None,
        "license": package.license,
        "summary": package.summary,
        "description": package.description,
        "url": package.url,
        "vendor": package.vendor,
        "packager": package.packager,
        "build_time": package.build_time_as_rfc3339() if package.build_time else None,
        "download_size": package.download_size,
        "install_size": package.install_size,
        "group": package.group,
        "source_rpm": package.source_rpm,
        "reason": package.reason,

        # Dependency lists (always arrays, may be empty)
        "provides": [_dependency_as_dict(dep) for dep in package.provides],
        "requires": [_dependency_as_dict(dep) for dep in package.requires],
        "requires_pre": [_dependency_as_dict(dep) for dep in package.requires_pre],
        "conflicts": [_dependency_as_dict(dep) for dep in package.conflicts],
        "obsoletes": [_dependency_as_dict(dep) for dep in package.obsoletes],
        "regular_requires": [_dependency_as_dict(dep) for dep in package.regular_requires],
        "recommends": [_dependency_as_dict(dep) for dep in package.recommends],
        "suggests": [_dependency_as_dict(dep) for dep in package.suggests],
        "enhances": [_dependency_as_dict(dep) for dep in package.enhances],
        "supplements": [_dependency_as_dict(dep) for dep in package.supplements],

        # File list (always array, may be empty)
        "files": package.files,
    }


def _repository_as_dict(repository: Repository) -> Dict[str, Any]:
    """
    Returns a dictionary representation of the repository.

    All fields from the Repository model are included for schema consistency.

    When repository.rhsm=True, SSL secret fields (sslcacert, sslclientkey, sslclientcert)
    are set to None as they contain host-specific RHSM secrets that should not be exposed.
    """
    d = {
        "id": repository.repo_id,
        "name": repository.name,
        "baseurl": repository.baseurl,
        "metalink": repository.metalink,
        "mirrorlist": repository.mirrorlist,
        "gpgcheck": repository.gpgcheck,
        "repo_gpgcheck": repository.repo_gpgcheck,
        "gpgkey": repository.gpgkey,
        "sslverify": repository.sslverify,
        "metadata_expire": repository.metadata_expire,
        "module_hotfixes": repository.module_hotfixes,
        "rhsm": repository.rhsm,
        # SSL secrets are set to None when using RHSM (host-specific secrets not applicable),
        # otherwise return the actual values from DNF (which may be empty strings if not configured)
        "sslcacert": None if repository.rhsm else repository.sslcacert,
        "sslclientkey": None if repository.rhsm else repository.sslclientkey,
        "sslclientcert": None if repository.rhsm else repository.sslclientcert,
    }
    return d


def serialize_response_dump(solver: str, result: DumpResult) -> Dict[str, Any]:
    return {
        "solver": solver,
        "packages": [_package_as_dict(package) for package in result.packages],
        "repos": {repository.repo_id: _repository_as_dict(repository) for repository in result.repositories},
    }


def serialize_response_search(solver: str, result: SearchResult) -> Dict[str, Any]:
    return {
        "solver": solver,
        "packages": [_package_as_dict(package) for package in result.packages],
        "repos": {repository.repo_id: _repository_as_dict(repository) for repository in result.repositories},
    }


def _transactions_to_disjoint_sets(transactions: List[List[Package]]) -> List[List[Package]]:
    """
    Convert a list of transactions to a list of disjoint sets of packages.

    Solver implementations always return transactions as supersets of the previous transaction results.
    This function converts the transactions to a list of disjoint sets of packages, where each transaction result contains
    only the new "to be installed" packages.
    """
    disjoint_sets: List[List[Package]] = []
    seen_packages: Set[Package] = set()
    for transaction in transactions:
        current_set = set(transaction)
        disjoint_transaction = list(current_set - seen_packages)
        seen_packages.update(disjoint_transaction)
        # NOTE: we sort the transaction to ensure that the transaction results are
        # kept sorted in the same way as the original transactions.
        disjoint_transaction.sort()
        disjoint_sets.append(disjoint_transaction)
    return disjoint_sets


def serialize_response_depsolve(solver: str, result: DepsolveResult) -> Dict[str, Any]:
    """
    Serializes a Solver API response for the DEPSOLVE command.

    The response is designed to be convenient for the osbuild/images implementation.
    Specifically, the response will be used to generate multiple instances of the org.osbuild.rpm stage
    in a manifest to install the packages in groups in the same order as the transactions.
    For this reason, we do not return the transactions results as supersets of the previous transaction results,
    but rather post-process the data to generate transactions results, where each transaction result contains
    only the new "to be installed" packages. Effectively making the transactions results disjoint sets of packages.

    Example response:
    {
        "solver": "<solver name>",
        "transactions": [
            [
                {
                    "name": "bash",
                    "epoch": 0,
                    "version": "5.1.8",
                    "release": "9.el9",
                    "arch": "x86_64",
                    "repo_id": "fedora",
                    "location": "Packages/bash-5.1.8-9.el9.x86_64.rpm",
                    "remote_locations": ["https://example.com/fedora/Packages/bash-5.1.8-9.el9.x86_64.rpm"],
                    "checksum": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "license": "GPLv2+",
                    "summary": "The GNU Bourne Again shell",
                    "description": "The GNU Bourne Again shell",
                    ...
                },
                {
                    "name": "glibc",
                    "epoch": 0,
                    "version": "2.33",
                    "release": "1.fc33",
                    "arch": "x86_64",
                    "repo_id": "fedora",
                    "location": "Packages/glibc-2.33-1.fc33.x86_64.rpm",
                    "remote_locations": ["https://example.com/fedora/Packages/glibc-2.33-1.fc33.x86_64.rpm"],
                    "checksum": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    "license": "LGPLv2+",
                    "summary": "The GNU C Library",
                    "description": "The GNU C Library",
                    ...
                }
            ],
            [
                {
                    "name": "libstdc++",
                    "epoch": 0,
                    "version": "11.0.1",
                    "release": "1.fc33",
                    "arch": "x86_64",
                    "repo_id": "fedora",
                    "location": "Packages/libstdc++-11.0.1-1.fc33.x86_64.rpm",
                    "remote_locations": ["https://example.com/fedora/Packages/libstdc++-11.0.1-1.fc33.x86_64.rpm"],
                    "checksum": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
                    "license": "GPLv2+",
                    "summary": "The GNU Standard C++ Library",
                    "description": "The GNU Standard C++ Library",
                    ...
                }
            ],
            ...
        ],
        "repos": {
            "fedora": {
                "id": "fedora",
                "name": "Fedora",
                "baseurl": ["https://example.com/fedora"],
            }
        },
        "modules": {...},
        "sbom": {...},
    }
    """

    transactions = _transactions_to_disjoint_sets(result.transactions)
    transactions_as_dicts = []
    for transaction in transactions:
        transactions_as_dicts.append([_package_as_dict(package) for package in transaction])

    d = {
        "solver": solver,
        "transactions": transactions_as_dicts,
        "repos": {repository.repo_id: _repository_as_dict(repository) for repository in result.repositories},
        "modules": result.modules or {},
    }

    if result.sbom:
        d["sbom"] = result.sbom

    return d


# pylint: disable=too-many-branches
def _parse_repository(repo_dict: Dict[str, Any]) -> Repository:
    """
    Parse repository config from dict.

    Note: V2 API only supports 'gpgkey' as a list. Unlike V1, it does not support
    'gpgkey' as a string or merge 'gpgkey' and 'gpgkeys' fields.
    """

    if not isinstance(repo_dict, dict):
        raise TypeError("Repository config must be a dict")

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
    if "gpgkey" in repo_dict:
        gpgkey_value = repo_dict["gpgkey"]
        if not isinstance(gpgkey_value, list):
            raise TypeError(f"'gpgkey' must be a list, got {type(gpgkey_value).__name__}")
        kwargs["gpgkey"] = gpgkey_value
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
    if "rhsm" in repo_dict:
        kwargs["rhsm"] = repo_dict["rhsm"]

    return Repository.from_request(**kwargs)


def _parse_depsolve_transaction(trans_dict: Dict[str, Any]) -> DepsolveTransaction:
    """Parse a transaction from a dict"""

    if not isinstance(trans_dict, dict):
        raise TypeError("Depsolve transaction must be a dict")

    kwargs = {
        "package_specs": trans_dict.get("package-specs", []),
    }

    if not kwargs["package_specs"]:
        raise ValueError("Depsolve transaction must contain at least one package specification")

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
    """Parse a V2 request dict into a SolverRequest object"""
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
    if "transactions" in arguments:
        if not isinstance(arguments["transactions"], list):
            raise InvalidRequestError("Field 'transactions' must be a list")
        try:
            depsolve_transactions = [_parse_depsolve_transaction(t) for t in arguments["transactions"]]
        except (ValueError, TypeError) as e:
            raise InvalidRequestError(f"Invalid depsolve transaction: {e}") from e
        except KeyError as e:
            raise InvalidRequestError(f"Missing required field {e} in 'transactions' list") from e

    search_args = None
    if "search" in arguments:
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
        api_version=SolverAPIVersion.V2,
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
