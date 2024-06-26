"""Defines standard-agnostic data model for an SBOM."""

import abc
import urllib.parse
import uuid
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Set


class ChecksumAlgorithm(Enum):
    SHA1 = auto()
    SHA224 = auto()
    SHA256 = auto()
    SHA384 = auto()
    SHA512 = auto()
    MD5 = auto()


class BasePackage(abc.ABC):
    """Represents a software package."""

    # pylint: disable=too-many-instance-attributes
    def __init__(
        self,
        name: str,
        version: str,
        filename: str = "",
        license_declared: str = "",
        vendor: str = "",
        checksums: Optional[Dict[ChecksumAlgorithm, str]] = None,
        homepage: str = "",
        download_url: str = "",
        build_date: Optional[datetime] = None,
        summary: str = "",
        description: str = "",
        depends_on: Optional[Set["BasePackage"]] = None,
        optional_depends_on: Optional[Set["BasePackage"]] = None,
    ) -> None:
        self.name = name
        self.version = version
        self.filename = filename
        self.license_declared = license_declared
        self.vendor = vendor
        self.checksums = checksums or {}
        self.homepage = homepage
        self.download_url = download_url
        self.build_date = build_date
        self.summary = summary
        self.description = description
        self.depends_on = depends_on or set()
        self.optional_depends_on = optional_depends_on or set()

    @abc.abstractmethod
    def uuid(self) -> str:
        """
        Returns a stable UUID for the package.
        """

    @abc.abstractmethod
    def source_info(self) -> str:
        """
        Return a string describing the source of the package.
        """

    @abc.abstractmethod
    def purl(self) -> str:
        """
        Return a Package URL for the package.

        The PURL format is:
        pkg:<type>/<namespace>/<name>@<version>?<qualifiers>#<subpath>

        Core PURL spec is defined at:
        https://github.com/package-url/purl-spec/blob/master/PURL-SPECIFICATION.rst
        """


class RPMDependency:
    """Represents an RPM dependency or provided capability."""

    def __init__(self, name: str, relation: str = "", version: str = "") -> None:
        self.name = name
        self.relation = relation
        self.version = version

    def __str__(self) -> str:
        return f"{self.name} {self.relation} {self.version}"


class RPMPackage(BasePackage):
    """Represents an RPM package."""

    def __init__(
        self,
        name: str,
        version: str,
        release: str,
        architecture: str,
        epoch: int = 0,
        filename: str = "",
        license_declared: str = "",
        vendor: str = "",
        checksums: Optional[Dict[ChecksumAlgorithm, str]] = None,
        homepage: str = "",
        download_url: str = "",
        build_date: Optional[datetime] = None,
        summary: str = "",
        description: str = "",
        depends_on: Optional[Set["BasePackage"]] = None,
        optional_depends_on: Optional[Set["BasePackage"]] = None,
        repository_url: str = "",
        source_rpm: str = "",
        rpm_provides: Optional[List[RPMDependency]] = None,
        rpm_requires: Optional[List[RPMDependency]] = None,
        rpm_recommends: Optional[List[RPMDependency]] = None,
        rpm_suggests: Optional[List[RPMDependency]] = None,
    ) -> None:
        super().__init__(
            name,
            version,
            filename,
            license_declared,
            vendor,
            checksums,
            homepage,
            download_url,
            build_date,
            summary,
            description,
            depends_on,
            optional_depends_on,
        )
        self.release = release
        self.architecture = architecture
        self.epoch = epoch
        self.repository_url = repository_url
        self.source_rpm = source_rpm
        self.rpm_provides = rpm_provides or []
        self.rpm_requires = rpm_requires or []
        self.rpm_recommends = rpm_recommends or []
        self.rpm_suggests = rpm_suggests or []

    def source_info(self) -> str:
        """
        Return a string describing the source of the RPM package.
        """
        if self.source_rpm:
            return f"Source RPM: {self.source_rpm}"
        return ""

    def uuid(self) -> str:
        """
        Returns a stable UUID for the same RPM package as defined by the PURL.
        """
        return str(uuid.uuid3(uuid.NAMESPACE_URL, self._purl(with_repo_url=False)))

    def _purl(self, with_repo_url=True) -> str:
        """
        Return a Package URL for the RPM package.

        Optionally don't include the repository URL in the PURL. This is useful
        to generate a PURL that can be used to identify the same package, regardless
        of the repository it was found in.

        PURL spec for RPMs is defined at:
        https://github.com/package-url/purl-spec/blob/master/PURL-TYPES.rst#rpm
        """
        namespace = ""
        if self.vendor:
            namespace = f"{urllib.parse.quote(self.vendor.lower())}/"

        purl = f"pkg:rpm/{namespace}{self.name}@{self.version}-{self.release}?arch={self.architecture}"

        if self.epoch:
            purl += f"&epoch={self.epoch}"

        if with_repo_url and self.repository_url:
            # https://github.com/package-url/purl-spec/blob/master/PURL-SPECIFICATION.rst#character-encoding
            purl += f"&repository_url={urllib.parse.quote(self.repository_url, safe='/:=')}"

        return purl

    def purl(self) -> str:
        return self._purl()
