"""
Core domain model for the solver

This module contains data classes representing the fundamental domain objects
used by the solver: packages, repositories, dependencies, and checksums.

These models are used internally by solver implementations and in API responses.
"""

import json
from datetime import datetime, timezone
from typing import FrozenSet, List, Optional


def _validate_kwargs(kwargs: dict, allowed: FrozenSet[str], class_name: str) -> None:
    """
    Helper function for data classes to validate that kwargs only contains allowed keys.

    Raises:
        ValueError: If unrecognized keyword arguments are provided.
    """
    unrecognized = set(kwargs.keys()) - allowed
    if unrecognized:
        raise ValueError(
            f"{class_name}: unrecognized keyword arguments: {', '.join(sorted(unrecognized))}"
        )


# pylint: disable=too-many-instance-attributes
class Repository:
    """
    Represents a DNF / YUM repository

    XXX: This class could be extended to represent more repository attributes common across DNF4 and DNF5.
    """

    _ALLOWED_KWARGS = frozenset({
        "metalink",
        "mirrorlist",
        "gpgcheck",
        "repo_gpgcheck",
        "gpgkeys",
        "sslverify",
        "sslcacert",
        "sslclientkey",
        "sslclientcert",
    })

    def __init__(self, repo_id: str, name: str, baseurl: Optional[List[str]] = None, **kwargs) -> None:
        _validate_kwargs(kwargs, self._ALLOWED_KWARGS, self.__class__.__name__)

        self.repo_id = repo_id
        self.name = name
        self.baseurl = baseurl
        self.metalink: Optional[str] = kwargs.get("metalink")
        self.mirrorlist: Optional[str] = kwargs.get("mirrorlist")
        self.gpgcheck: Optional[bool] = kwargs.get("gpgcheck")
        self.repo_gpgcheck: Optional[bool] = kwargs.get("repo_gpgcheck")
        self.gpgkeys: List[str] = kwargs.get("gpgkeys", [])
        self.sslverify: Optional[bool] = kwargs.get("sslverify")
        self.sslcacert: Optional[str] = kwargs.get("sslcacert")
        self.sslclientkey: Optional[str] = kwargs.get("sslclientkey")
        self.sslclientcert: Optional[str] = kwargs.get("sslclientcert")

        if not any([self.baseurl, self.metalink, self.mirrorlist]):
            raise ValueError("At least one of 'baseurl', 'metalink', or 'mirrorlist' must be specified")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Repository):
            return False
        return (
            self.repo_id == other.repo_id
            and self.name == other.name
            and self.baseurl == other.baseurl
            and self.metalink == other.metalink
            and self.mirrorlist == other.mirrorlist
            and self.gpgcheck == other.gpgcheck
            and self.repo_gpgcheck == other.repo_gpgcheck
            and self.gpgkeys == other.gpgkeys
            and self.sslverify == other.sslverify
            and self.sslcacert == other.sslcacert
            and self.sslclientkey == other.sslclientkey
            and self.sslclientcert == other.sslclientcert
        )

    def __hash__(self) -> int:
        return hash((
            self.repo_id,
            self.name,
            tuple(self.baseurl) if self.baseurl else None,
            self.metalink,
            self.mirrorlist,
            self.gpgcheck,
            self.repo_gpgcheck,
            tuple(self.gpgkeys) if self.gpgkeys else None,
            self.sslverify,
            self.sslcacert,
            self.sslclientkey,
            self.sslclientcert,
        ))

    def __repr__(self) -> str:
        return f"Repository(repo_id='{self.repo_id}', name='{self.name}', baseurl={self.baseurl}, " \
            f"metalink='{self.metalink}', mirrorlist='{self.mirrorlist}', gpgcheck={self.gpgcheck}, " \
            f"repo_gpgcheck={self.repo_gpgcheck}, gpgkeys={self.gpgkeys}, sslverify={self.sslverify}, " \
            f"sslcacert='{self.sslcacert}', sslclientkey='{self.sslclientkey}', sslclientcert='{self.sslclientcert}')"


class Dependency:
    """
    Represents an RPM dependency or provided capability.

    XXX: handle rich dependencies (e.g. "(libbpf >= 2:1.4.7 if libbpf)" or "(util-linux-core or util-linux)").
    """

    def __init__(self, name: str, relation: str = "", version: str = "") -> None:
        self.name = name
        self.relation = relation
        self.version = version

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Dependency):
            return False
        return (
            self.name == other.name
            and self.relation == other.relation
            and self.version == other.version
        )

    def __hash__(self) -> int:
        return hash((self.name, self.relation, self.version))

    def __repr__(self) -> str:
        return f"Dependency(name='{self.name}', relation='{self.relation}', version='{self.version}')"

    def __str__(self) -> str:
        s = self.name
        if self.relation:
            s += f" {self.relation}"
        if self.version:
            s += f" {self.version}"
        return s


class Checksum:
    """Reresents a checksum used by RPM packages."""

    def __init__(self, algorithm: str, value: str) -> None:
        self.algorithm = algorithm
        self.value = value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Checksum):
            return False
        return self.algorithm == other.algorithm and self.value == other.value

    def __hash__(self) -> int:
        return hash((self.algorithm, self.value))

    def __repr__(self) -> str:
        return f"Checksum(algorithm='{self.algorithm}', value='{self.value}')"

    def __str__(self) -> str:
        return f"{self.algorithm}:{self.value}"


# pylint: disable=too-many-instance-attributes
class Package:
    """
    Represents an RPM package

    Based on libdnf5 (https://github.com/rpm-software-management/dnf5/blob/main/include/libdnf5/rpm/package.hpp) and
    DNF4 libdnf(https://github.com/rpm-software-management/libdnf/blob/dnf-4-master/libdnf/hy-package.h).

    Values are a common subset of the values in the libdnf5 and libdnf packages, which are relevant for image building.
    """

    _ALLOWED_KWARGS = frozenset({
        "group",
        "download_size",
        "install_size",
        "license",
        "source_rpm",
        "build_time",
        "packager",
        "vendor",
        "url",
        "summary",
        "description",
        "provides",
        "requires",
        "requires_pre",
        "conflicts",
        "obsoletes",
        "regular_requires",
        "recommends",
        "suggests",
        "enhances",
        "supplements",
        "files",
        "location",
        "remote_locations",
        "checksum",
        "header_checksum",
        "repo_id",
        "reason",
    })

    def __init__(self, name: str, version: str, release: str, arch: str, epoch: int = 0, **kwargs) -> None:
        _validate_kwargs(kwargs, self._ALLOWED_KWARGS, self.__class__.__name__)

        self.name = name
        self.version = version
        self.release = release
        self.arch = arch
        self.epoch = epoch

        self.group: Optional[str] = kwargs.get("group")
        self.download_size: Optional[int] = kwargs.get("download_size")
        self.install_size: Optional[int] = kwargs.get("install_size")
        self.license: Optional[str] = kwargs.get("license")
        self.source_rpm: Optional[str] = kwargs.get("source_rpm")
        self.build_time: Optional[int] = kwargs.get("build_time")
        self.packager: Optional[str] = kwargs.get("packager")
        self.vendor: Optional[str] = kwargs.get("vendor")

        # RPM package URL (project home address)
        self.url: Optional[str] = kwargs.get("url")

        self.summary: Optional[str] = kwargs.get("summary")
        self.description: Optional[str] = kwargs.get("description")

        # Regular dependencies
        self.provides: List[Dependency] = kwargs.get("provides", [])
        self.requires: List[Dependency] = kwargs.get("requires", [])
        self.requires_pre: List[Dependency] = kwargs.get("requires_pre", [])
        self.conflicts: List[Dependency] = kwargs.get("conflicts", [])
        self.obsoletes: List[Dependency] = kwargs.get("obsoletes", [])
        self.regular_requires: List[Dependency] = kwargs.get("regular_requires", [])

        # Weak dependencies
        self.recommends: List[Dependency] = kwargs.get("recommends", [])
        self.suggests: List[Dependency] = kwargs.get("suggests", [])
        self.enhances: List[Dependency] = kwargs.get("enhances", [])
        self.supplements: List[Dependency] = kwargs.get("supplements", [])

        # List of files and directories the RPM package contains
        self.files: List[str] = kwargs.get("files", [])

        # RPM package relative path/location from repodata
        self.location: Optional[str] = kwargs.get("location")
        # RPM package remote location where the package can be download from
        self.remote_locations: List[str] = kwargs.get("remote_locations", [])

        # Checksum object representing RPM package checksum and its type
        self.checksum: Optional[Checksum] = kwargs.get("checksum")
        # Checksum object representing RPM package header checksum and its type
        self.header_checksum: Optional[Checksum] = kwargs.get("header_checksum")
        # Repository ID this package belongs to
        self.repo_id: Optional[str] = kwargs.get("repo_id")
        # Resolved reason why a package was / would be installed.
        self.reason: Optional[str] = kwargs.get("reason")

    def full_nevra(self) -> str:
        return f"{self.name}-{self.epoch}:{self.version}-{self.release}.{self.arch}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Package):
            return False
        return (
            self.name == other.name
            and self.version == other.version
            and self.release == other.release
            and self.arch == other.arch
            and self.epoch == other.epoch
            and self.group == other.group
            and self.download_size == other.download_size
            and self.install_size == other.install_size
            and self.license == other.license
            and self.source_rpm == other.source_rpm
            and self.build_time == other.build_time
            and self.packager == other.packager
            and self.vendor == other.vendor
            and self.url == other.url
            and self.summary == other.summary
            and self.description == other.description
            and self.provides == other.provides
            and self.requires == other.requires
            and self.requires_pre == other.requires_pre
            and self.conflicts == other.conflicts
            and self.obsoletes == other.obsoletes
            and self.regular_requires == other.regular_requires
            and self.recommends == other.recommends
            and self.suggests == other.suggests
            and self.enhances == other.enhances
            and self.supplements == other.supplements
            and self.files == other.files
            and self.location == other.location
            and self.remote_locations == other.remote_locations
            and self.checksum == other.checksum
            and self.header_checksum == other.header_checksum
            and self.repo_id == other.repo_id
            and self.reason == other.reason
        )

    def __hash__(self) -> int:
        # Convert lists to tuples for hashing
        return hash((
            self.name,
            self.version,
            self.release,
            self.arch,
            self.epoch,
            self.group,
            self.download_size,
            self.install_size,
            self.license,
            self.source_rpm,
            self.build_time,
            self.packager,
            self.vendor,
            self.url,
            self.summary,
            self.description,
            tuple(self.provides),
            tuple(self.requires),
            tuple(self.requires_pre),
            tuple(self.conflicts),
            tuple(self.obsoletes),
            tuple(self.regular_requires),
            tuple(self.recommends),
            tuple(self.suggests),
            tuple(self.enhances),
            tuple(self.supplements),
            tuple(self.files),
            self.location,
            tuple(self.remote_locations) if self.remote_locations else None,
            self.checksum,
            self.header_checksum,
            self.repo_id,
            self.reason,
        ))

    def __lt__(self, other: "Package") -> bool:
        return self.full_nevra() < other.full_nevra()

    def __str__(self) -> str:
        return self.full_nevra()

    def __repr__(self) -> str:
        return f"Package(name='{self.name}', version='{self.version}', release='{self.release}', arch='{self.arch}', " \
            f"epoch={self.epoch}, group='{self.group}', download_size={self.download_size}, " \
            f"install_size={self.install_size}, license='{self.license}', source_rpm='{self.source_rpm}', " \
            f"build_time={self.build_time}, packager='{self.packager}', vendor='{self.vendor}', url='{self.url}', " \
            f"summary='{self.summary}', description='{self.description}', provides={self.provides}, " \
            f"requires={self.requires}, requires_pre={self.requires_pre}, conflicts={self.conflicts}, " \
            f"obsoletes={self.obsoletes}, regular_requires={self.regular_requires}, recommends={self.recommends}, " \
            f"suggests={self.suggests}, enhances={self.enhances}, supplements={self.supplements}, " \
            f"files={self.files}, location='{self.location}', remote_locations={self.remote_locations}, " \
            f"checksum={self.checksum}, header_checksum={self.header_checksum}, repo_id='{self.repo_id}', " \
            f"reason='{self.reason}')"

    @staticmethod
    def _timestamp_to_rfc3339(timestamp: int) -> str:
        return datetime.fromtimestamp(timestamp, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    def build_time_as_rfc3339(self) -> str:
        if self.build_time is None:
            return ""
        return self._timestamp_to_rfc3339(self.build_time)


class DepsolveResult:
    """Result of a depsolve operation."""

    def __init__(
        self,
        packages: List[Package],
        repositories: List[Repository],
        modules: Optional[dict] = None,
        sbom: Optional[dict] = None
    ):
        self.packages = packages
        self.repositories = repositories
        self.modules = modules
        self.sbom = sbom

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DepsolveResult):
            return False
        return (
            self.packages == other.packages
            and self.repositories == other.repositories
            and self.modules == other.modules
            and self.sbom == other.sbom
        )

    def __hash__(self) -> int:
        return hash((
            tuple(self.packages),
            tuple(self.repositories),
            json.dumps(self.modules, sort_keys=True) if self.modules else None,
            json.dumps(self.sbom, sort_keys=True) if self.sbom else None,
        ))

    def __repr__(self) -> str:
        return f"DepsolveResult(packages={self.packages}, repositories={self.repositories}, " \
            f"modules={self.modules}, sbom={self.sbom})"


class DumpResult:
    """Result of a dump operation."""

    def __init__(self, packages: List[Package]):
        self.packages = packages

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DumpResult):
            return False
        return self.packages == other.packages

    def __hash__(self) -> int:
        return hash((tuple(self.packages)))

    def __repr__(self) -> str:
        return f"DumpResult(packages={self.packages})"


class SearchResult:
    """Result of a search operation."""

    def __init__(self, packages: List[Package]):
        self.packages = packages

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SearchResult):
            return False
        return self.packages == other.packages

    def __hash__(self) -> int:
        return hash((tuple(self.packages)))

    def __repr__(self) -> str:
        return f"SearchResult(packages={self.packages})"
