from typing import Any, Dict, List, Optional

from osbuild.solver.model import Package, Repository


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


def serialize_response_dump(packages: List[Package]) -> List[dict]:
    return [_package_as_dict_dump_search(package) for package in packages]


def serialize_response_search(packages: List[Package]) -> List[dict]:
    return [_package_as_dict_dump_search(package) for package in packages]


def serialize_response_depsolve(
    solver: str,
    packages: List[Package],
    repositories: List[Repository],
    modules: Optional[dict] = None,
    sbom: Optional[Any] = None,
) -> Dict[str, Any]:
    d = {
        "solver": solver,
        "packages": [_package_as_dict_depsolve(package) for package in packages],
        "repos": {repository.repo_id: _repository_as_dict(repository) for repository in repositories},
        "modules": modules if modules else {},
    }

    if sbom:
        d["sbom"] = sbom

    return d
