"""
Core domain model for the solver

This module contains data classes representing the fundamental domain objects
used by the solver: packages, repositories, dependencies, and checksums.

These models are used internally by solver implementations and in API responses.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Type, Union


class ValidatedModel:
    """
    Base class providing runtime validation of allowed model attributes and their types.

    Subclasses must define _ATTR_TYPES as a dictionary mapping attribute names to their allowed types:
        - Simple type: str, int, bool, list, etc.
        - Optional type: (type, type(None)) for Optional[type]

    Setting an unknown attribute or a value of the wrong type raises ValueError.
    Private attributes (starting with '_') bypass validation.

    Limitations:
        - For list attributes, only the container type (list) is validated, not the types of items within the list.
    """

    _ATTR_TYPES: Dict[str, Union[Type, Tuple[Type, ...]]] = {}

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if "_ATTR_TYPES" not in cls.__dict__ or not cls._ATTR_TYPES:
            raise TypeError(
                f"{cls.__name__} must define a non-empty '_ATTR_TYPES' class attribute"
            )

    def __setattr__(self, name: str, value: Any) -> None:
        # Allow private/internal attributes without validation
        if name.startswith("_"):
            super().__setattr__(name, value)
            return

        cls_name = self.__class__.__name__

        if name not in self._ATTR_TYPES:
            raise ValueError(f"{cls_name}: unknown attribute '{name}'")

        expected_types = self._ATTR_TYPES[name]

        if not isinstance(value, expected_types):
            # Format type name for error message
            if isinstance(expected_types, tuple):
                # NOTE: 't' is a type, not a variable, so we need to use unidiomatic-typecheck.
                # pylint: disable=unidiomatic-typecheck
                type_names = ["None" if t is type(None) else t.__name__ for t in expected_types]
                type_str = " or ".join(type_names)
            else:
                type_str = expected_types.__name__
            raise ValueError(
                f"{cls_name}.{name}: expected {type_str}, got {type(value).__name__}"
            )

        super().__setattr__(name, value)


# pylint: disable=too-many-instance-attributes
class Repository(ValidatedModel):
    """
    Represents a DNF / YUM repository

    XXX: This class could be extended to represent more repository attributes common across DNF4 and DNF5.
    """

    # Request-specific defaults - centralized definition
    # These are applied when creating Repository from API requests via from_request()
    REQUEST_DEFAULTS = {
        "sslverify": True,
        # In dnf, the default metadata expiration time is 48 hours. However,
        # some repositories never expire the metadata, and others expire it much
        # sooner than that. We therefore allow this to be configured. If nothing
        # is provided we error on the side of checking if we should invalidate
        # the cache. If cache invalidation is not necessary, the overhead of
        # checking is in the hundreds of milliseconds. In order to avoid this
        # overhead accumulating for API calls that consist of several dnf calls,
        # we set the expiration to a short time period, rather than 0.
        "metadata_expire": "20s",
    }

    _ATTR_TYPES = {
        "repo_id": str,
        "baseurl": (list, type(None)),
        "name": str,
        "metalink": (str, type(None)),
        "mirrorlist": (str, type(None)),
        "gpgcheck": (bool, type(None)),
        "repo_gpgcheck": (bool, type(None)),
        "gpgkey": list,
        "sslverify": (bool, type(None)),
        "sslcacert": (str, type(None)),
        "sslclientkey": (str, type(None)),
        "sslclientcert": (str, type(None)),
        "metadata_expire": (str, type(None)),
        "module_hotfixes": (bool, type(None)),
        "enabled": (bool, type(None)),
        "priority": (int, type(None)),
        "username": (str, type(None)),
        "password": (str, type(None)),
        "skip_if_unavailable": (bool, type(None)),
        "rhsm": bool,
    }

    def __init__(
            self,
            repo_id: str,
            baseurl: Optional[List[str]] = None,
            **kwargs) -> None:
        """
        Create a Repository.

        For creating from API requests, use Repository.from_request() which applies
        request-specific defaults.
        """
        self.repo_id = repo_id
        self.baseurl = baseurl
        self.name: str = kwargs.pop("name", repo_id)
        self.metalink: Optional[str] = kwargs.pop("metalink", None)
        self.mirrorlist: Optional[str] = kwargs.pop("mirrorlist", None)
        self.gpgcheck: Optional[bool] = kwargs.pop("gpgcheck", None)
        self.repo_gpgcheck: Optional[bool] = kwargs.pop("repo_gpgcheck", None)
        self.gpgkey: List[str] = kwargs.pop("gpgkey", [])
        self.sslverify: Optional[bool] = kwargs.pop("sslverify", None)
        self.sslcacert: Optional[str] = kwargs.pop("sslcacert", None)
        self.sslclientkey: Optional[str] = kwargs.pop("sslclientkey", None)
        self.sslclientcert: Optional[str] = kwargs.pop("sslclientcert", None)
        self.metadata_expire: Optional[str] = kwargs.pop("metadata_expire", None)
        self.module_hotfixes: Optional[bool] = kwargs.pop("module_hotfixes", None)
        self.enabled: Optional[bool] = kwargs.pop("enabled", None)
        self.priority: Optional[int] = kwargs.pop("priority", None)
        self.username: Optional[str] = kwargs.pop("username", None)
        self.password: Optional[str] = kwargs.pop("password", None)
        self.skip_if_unavailable: Optional[bool] = kwargs.pop("skip_if_unavailable", None)

        # Additional fields not represented in the YUM/DNF repository configuration.

        # Whether this repository uses RHSM secrets from the host system to
        # access its content.
        # If True, the sslcacert, sslclientkey, and sslclientcert values should
        # be set by the Solver if such Repository objects are passed to its
        # constructor. Similarly, an API implementation may choose to omit these
        # values from the API response if this flag is True.
        self.rhsm: bool = kwargs.pop("rhsm", False)

        if kwargs:
            raise ValueError(
                f"{self.__class__.__name__}: unrecognized keyword arguments: {', '.join(sorted(kwargs.keys()))}"
            )

        if not any([self.baseurl, self.metalink, self.mirrorlist]):
            raise ValueError("At least one of 'baseurl', 'metalink', or 'mirrorlist' must be specified")

    @classmethod
    def from_request(
        cls,
        repo_id: str,
        baseurl: Optional[List[str]] = None,
        **kwargs
    ) -> "Repository":
        """
        Create a Repository from API request data, applying request-specific defaults.

        This is the preferred way to create Repository objects when parsing API requests.
        For converting from DNF repo objects, use the regular constructor which preserves
        the actual values without applying defaults.
        """
        # Apply request-specific defaults for fields not explicitly provided
        for field, default in cls.REQUEST_DEFAULTS.items():
            if field not in kwargs or kwargs[field] is None:
                kwargs[field] = default

        return cls(repo_id=repo_id, baseurl=baseurl, **kwargs)

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
            and self.gpgkey == other.gpgkey
            and self.sslverify == other.sslverify
            and self.sslcacert == other.sslcacert
            and self.sslclientkey == other.sslclientkey
            and self.sslclientcert == other.sslclientcert
            and self.metadata_expire == other.metadata_expire
            and self.module_hotfixes == other.module_hotfixes
            and self.enabled == other.enabled
            and self.priority == other.priority
            and self.username == other.username
            and self.password == other.password
            and self.skip_if_unavailable == other.skip_if_unavailable
            and self.rhsm == other.rhsm
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
            tuple(self.gpgkey) if self.gpgkey else None,
            self.sslverify,
            self.sslcacert,
            self.sslclientkey,
            self.sslclientcert,
            self.metadata_expire,
            self.module_hotfixes,
            self.enabled,
            self.priority,
            self.username,
            self.password,
            self.skip_if_unavailable,
            self.rhsm,
        ))

    def __repr__(self) -> str:
        return f"Repository(repo_id='{self.repo_id}', name='{self.name}', baseurl={self.baseurl}, " \
            f"metalink='{self.metalink}', mirrorlist='{self.mirrorlist}', gpgcheck={self.gpgcheck}, " \
            f"repo_gpgcheck={self.repo_gpgcheck}, gpgkey={self.gpgkey}, sslverify={self.sslverify}, " \
            f"sslcacert='{self.sslcacert}', sslclientkey='{self.sslclientkey}', " \
            f"sslclientcert='{self.sslclientcert}', metadata_expire='{self.metadata_expire}', " \
            f"module_hotfixes={self.module_hotfixes}, enabled={self.enabled}, priority={self.priority}, " \
            f"username='{self.username}', password='{self.password}', " \
            f"skip_if_unavailable={self.skip_if_unavailable}, rhsm={self.rhsm})"


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
class Package(ValidatedModel):
    """
    Represents an RPM package

    Based on libdnf5 (https://github.com/rpm-software-management/dnf5/blob/main/include/libdnf5/rpm/package.hpp) and
    DNF4 libdnf(https://github.com/rpm-software-management/libdnf/blob/dnf-4-master/libdnf/hy-package.h).

    Values are a common subset of the values in the libdnf5 and libdnf packages, which are relevant for image building.
    """

    _ATTR_TYPES = {
        "name": str,
        "version": str,
        "release": str,
        "arch": str,
        "epoch": int,
        "group": (str, type(None)),
        "download_size": (int, type(None)),
        "install_size": (int, type(None)),
        "license": (str, type(None)),
        "source_rpm": (str, type(None)),
        "build_time": (int, type(None)),
        "packager": (str, type(None)),
        "vendor": (str, type(None)),
        "url": (str, type(None)),
        "summary": (str, type(None)),
        "description": (str, type(None)),
        # Regular dependencies
        "provides": list,
        "requires": list,
        "requires_pre": list,
        "conflicts": list,
        "obsoletes": list,
        "regular_requires": list,
        # Weak dependencies
        "recommends": list,
        "suggests": list,
        "enhances": list,
        "supplements": list,
        # Files
        "files": list,
        # Location
        "location": (str, type(None)),
        "remote_locations": list,
        # Checksums
        "checksum": (Checksum, type(None)),
        "header_checksum": (Checksum, type(None)),
        # Metadata
        "repo_id": (str, type(None)),
        "reason": (str, type(None)),
    }

    def __init__(self, name: str, version: str, release: str, arch: str, epoch: int = 0, **kwargs) -> None:
        self.name = name
        self.version = version
        self.release = release
        self.arch = arch
        self.epoch = epoch

        self.group: Optional[str] = kwargs.pop("group", None)
        self.download_size: Optional[int] = kwargs.pop("download_size", None)
        self.install_size: Optional[int] = kwargs.pop("install_size", None)
        self.license: Optional[str] = kwargs.pop("license", None)
        self.source_rpm: Optional[str] = kwargs.pop("source_rpm", None)
        self.build_time: Optional[int] = kwargs.pop("build_time", None)
        self.packager: Optional[str] = kwargs.pop("packager", None)
        self.vendor: Optional[str] = kwargs.pop("vendor", None)

        # RPM package URL (project home address)
        self.url: Optional[str] = kwargs.pop("url", None)

        self.summary: Optional[str] = kwargs.pop("summary", None)
        self.description: Optional[str] = kwargs.pop("description", None)

        # Regular dependencies
        self.provides: List[Dependency] = kwargs.pop("provides", [])
        self.requires: List[Dependency] = kwargs.pop("requires", [])
        self.requires_pre: List[Dependency] = kwargs.pop("requires_pre", [])
        self.conflicts: List[Dependency] = kwargs.pop("conflicts", [])
        self.obsoletes: List[Dependency] = kwargs.pop("obsoletes", [])
        self.regular_requires: List[Dependency] = kwargs.pop("regular_requires", [])

        # Weak dependencies
        self.recommends: List[Dependency] = kwargs.pop("recommends", [])
        self.suggests: List[Dependency] = kwargs.pop("suggests", [])
        self.enhances: List[Dependency] = kwargs.pop("enhances", [])
        self.supplements: List[Dependency] = kwargs.pop("supplements", [])

        # List of files and directories the RPM package contains
        self.files: List[str] = kwargs.pop("files", [])

        # RPM package relative path/location from repodata
        self.location: Optional[str] = kwargs.pop("location", None)
        # RPM package remote location where the package can be download from
        self.remote_locations: List[str] = kwargs.pop("remote_locations", [])

        # Checksum object representing RPM package checksum and its type
        self.checksum: Optional[Checksum] = kwargs.pop("checksum", None)
        # Checksum object representing RPM package header checksum and its type
        self.header_checksum: Optional[Checksum] = kwargs.pop("header_checksum", None)
        # Repository ID this package belongs to
        self.repo_id: Optional[str] = kwargs.pop("repo_id", None)
        # Resolved reason why a package was / would be installed.
        self.reason: Optional[str] = kwargs.pop("reason", None)

        if kwargs:
            raise ValueError(
                f"{self.__class__.__name__}: unrecognized keyword arguments: {', '.join(sorted(kwargs.keys()))}"
            )

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
        transactions: List[List[Package]],
        repositories: List[Repository],
        modules: Optional[dict] = None,
        sbom: Optional[dict] = None
    ):
        """
        Args:
            transactions: List of transaction results, each containing a list of packages that are a result of
                          dependency resolution. The order of transactions corresponds to the order of transactions
                          in the request. Each transaction result is a superset of the previous transaction result.
                          The package list in each transaction is expected to be alphabetically sorted by full NEVRA.
            repositories: List of repositories used in the transactions.
            modules: Optional dictionary of modules-related information.
            sbom: Optional SBOM document for the transaction.
        """
        self.transactions = transactions
        self.repositories = repositories
        self.modules = modules
        self.sbom = sbom

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DepsolveResult):
            return False
        return (
            self.transactions == other.transactions
            and self.repositories == other.repositories
            and self.modules == other.modules
            and self.sbom == other.sbom
        )

    def __hash__(self) -> int:
        return hash((
            tuple((tuple(transaction) for transaction in self.transactions)),
            tuple(self.repositories),
            json.dumps(self.modules, sort_keys=True) if self.modules else None,
            json.dumps(self.sbom, sort_keys=True) if self.sbom else None,
        ))

    def __repr__(self) -> str:
        return f"DepsolveResult(transactions={self.transactions}, repositories={self.repositories}, " \
            f"modules={self.modules}, sbom={self.sbom})"


class DumpResult:
    """Result of a dump operation."""

    def __init__(self, packages: List[Package], repositories: List[Repository]):
        self.packages = packages
        self.repositories = repositories

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DumpResult):
            return False
        return self.packages == other.packages and self.repositories == other.repositories

    def __hash__(self) -> int:
        return hash((tuple(self.packages), tuple(self.repositories)))

    def __repr__(self) -> str:
        return f"DumpResult(packages={self.packages}, repositories={self.repositories})"


class SearchResult:
    """Result of a search operation."""

    def __init__(self, packages: List[Package], repositories: List[Repository]):
        self.packages = packages
        self.repositories = repositories

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SearchResult):
            return False
        return self.packages == other.packages and self.repositories == other.repositories

    def __hash__(self) -> int:
        return hash((tuple(self.packages), tuple(self.repositories)))

    def __repr__(self) -> str:
        return f"SearchResult(packages={self.packages}, repositories={self.repositories})"
