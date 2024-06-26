"""
A base implementation of SPDX 2.3 model, as described on:
https://spdx.github.io/spdx-spec/v2.3/
"""

import re
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Dict, List, Optional, Union


class CreatorType(Enum):
    """Enumeration of SPDX actor types."""

    PERSON = auto()
    ORGANIZATION = auto()
    TOOL = auto()

    def __str__(self) -> str:
        return self.name.capitalize()


class Creator():
    """Represents a Creator in SPDX."""

    def __init__(self, creator_type: CreatorType, name: str, email: Optional[str] = None) -> None:
        self.creator_type = creator_type
        self.name = name
        self.email = email

    def __str__(self):
        email_str = f" ({self.email})" if self.email else ""
        return f"{self.creator_type}: {self.name}{email_str}"


class EntityWithSpdxId():
    """
    Represents an SPDX entity with an SPDX ID.

    https://spdx.github.io/spdx-spec/v2.3/package-information/#72-package-spdx-identifier-field
    """

    def __init__(self, spdx_id: str) -> None:
        id_regex = re.compile(r"^SPDXRef-[a-zA-Z0-9\.\-]+$")
        if not id_regex.match(spdx_id):
            raise ValueError(f"Invalid SPDX ID '{spdx_id}'")
        self.spdx_id = spdx_id


def datetime_to_iso8601(dt: datetime) -> str:
    """
    Converts a datetime object to an SPDX-compliant ISO8601 string.

    This means that:
    - The timezone is UTC
    - The microsecond part is removed

    https://spdx.github.io/spdx-spec/v2.3/document-creation-information/#69-created-field
    """

    date = dt.astimezone(timezone.utc)
    date = date.replace(tzinfo=None)
    # Microseconds are not supported by SPDX
    date = date.replace(microsecond=0)
    return date.isoformat() + "Z"


class CreationInfo(EntityWithSpdxId):
    """
    Represents SPDX creation information.

    https://spdx.github.io/spdx-spec/v2.3/document-creation-information/
    """

    def __init__(
        self,
        spdx_version: str,
        spdx_id: str,
        name: str,
        document_namespace: str,
        creators: List[Creator],
        created: datetime,
        data_license: str = "CC0-1.0",
    ) -> None:
        super().__init__(spdx_id)

        if not spdx_version.startswith("SPDX-"):
            raise ValueError(f"Invalid SPDX version '{spdx_version}'")

        if spdx_id != "SPDXRef-DOCUMENT":
            raise ValueError(f"Invalid SPDX ID '{spdx_id}'")

        self.spdx_version = spdx_version
        self.name = name
        self.data_license = data_license
        self.document_namespace = document_namespace
        self.creators = creators
        self.created = created

    def to_dict(self):
        return {
            "SPDXID": self.spdx_id,
            "creationInfo": {
                "created": datetime_to_iso8601(self.created),
                "creators": [str(creator) for creator in self.creators],
            },
            "dataLicense": self.data_license,
            "name": self.name,
            "spdxVersion": self.spdx_version,
            "documentNamespace": self.document_namespace,
        }


class NoAssertionValue():
    """Represents the SPDX No Assertion value."""

    VALUE = "NOASSERTION"

    def __str__(self):
        return self.VALUE


class NoneValue():
    """Represents the SPDX None value."""

    VALUE = "NONE"

    def __str__(self):
        return self.VALUE


class ExternalPackageRefCategory(Enum):
    """Enumeration of external package reference categories."""

    SECURITY = auto()
    PACKAGE_MANAGER = auto()
    PERSISTENT_ID = auto()
    OTHER = auto()

    def __str__(self) -> str:
        return self.name.replace("_", "-")


CATEGORY_TO_REPOSITORY_TYPE: Dict[ExternalPackageRefCategory, List[str]] = {
    ExternalPackageRefCategory.SECURITY: ["cpe22Type", "cpe23Type", "advisory", "fix", "url", "swid"],
    ExternalPackageRefCategory.PACKAGE_MANAGER: ["maven-central", "nuget", "bower", "purl"],
    ExternalPackageRefCategory.PERSISTENT_ID: ["swh", "gitoid"],
    ExternalPackageRefCategory.OTHER: [],
}


class ExternalPackageRef():
    """
    Represents an external package reference.

    https://spdx.github.io/spdx-spec/v2.3/package-information/#721-external-reference-field
    """

    def __init__(self, category: ExternalPackageRefCategory, reference_type: str, locator: str) -> None:
        if len(CATEGORY_TO_REPOSITORY_TYPE[category]
               ) > 0 and reference_type not in CATEGORY_TO_REPOSITORY_TYPE[category]:
            raise ValueError(f"Invalid repository type '{reference_type}' for category '{category}'")

        self.category = category
        self.reference_type = reference_type
        self.locator = locator

    def to_dict(self):
        return {
            "referenceCategory": str(self.category),
            "referenceType": self.reference_type,
            "referenceLocator": self.locator,
        }


class ChecksumAlgorithm(Enum):
    """Enumeration of SPDX checksum algorithms."""

    SHA1 = auto()
    SHA224 = auto()
    SHA256 = auto()
    SHA384 = auto()
    SHA512 = auto()
    SHA3_256 = auto()
    SHA3_384 = auto()
    SHA3_512 = auto()
    BLAKE2b_256 = auto()
    BLAKE2b_384 = auto()
    BLAKE2b_512 = auto()
    BLAKE3 = auto()
    MD2 = auto()
    MD4 = auto()
    MD5 = auto()
    MD6 = auto()
    ADLER32 = auto()

    def __str__(self) -> str:
        return self.name.replace("_", "-")


class Checksum():
    """
    Represents a checksum.

    https://spdx.github.io/spdx-spec/v2.3/package-information/#72-checksum-fields
    """

    def __init__(self, algorithm: ChecksumAlgorithm, value: str) -> None:
        self.algorithm = algorithm
        self.value = value

    def to_dict(self):
        return {
            "algorithm": str(self.algorithm),
            "checksumValue": self.value,
        }


# pylint: disable=too-many-instance-attributes
class Package(EntityWithSpdxId):
    """Represents an SPDX package."""

    def __init__(
        self,
        spdx_id: str,
        name: str,
        download_location: Union[str, NoAssertionValue, NoneValue],
        version: Optional[str] = None,
        files_analyzed: Optional[bool] = None,
        checksums: Optional[List[Checksum]] = None,
        homepage: Optional[Union[str, NoAssertionValue, NoneValue]] = None,
        source_info: Optional[str] = None,
        license_declared: Optional[Union[str, NoAssertionValue, NoneValue]] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        external_references: Optional[List[ExternalPackageRef]] = None,
        built_date: Optional[datetime] = None,
    ) -> None:
        super().__init__(spdx_id)
        self.name = name
        self.download_location = download_location
        self.version = version
        self.files_analyzed = files_analyzed
        self.checksums = checksums or []
        self.homepage = homepage
        self.source_info = source_info
        self.license_declared = license_declared
        self.summary = summary
        self.description = description
        self.external_references = external_references or []
        self.built_date = built_date

    def to_dict(self):
        d = {
            "SPDXID": self.spdx_id,
            "name": self.name,
            "downloadLocation": str(self.download_location)
        }
        if self.files_analyzed is not None:
            d["filesAnalyzed"] = self.files_analyzed
        if self.version:
            d["versionInfo"] = self.version
        if self.checksums:
            d["checksums"] = [checksum.to_dict() for checksum in self.checksums]
        if self.homepage:
            d["homepage"] = str(self.homepage)
        if self.source_info:
            d["sourceInfo"] = self.source_info
        if self.license_declared:
            d["licenseDeclared"] = str(self.license_declared)
        if self.summary:
            d["summary"] = self.summary
        if self.description:
            d["description"] = self.description
        if self.external_references:
            d["externalRefs"] = [ref.to_dict() for ref in self.external_references]
        if self.built_date:
            d["builtDate"] = datetime_to_iso8601(self.built_date)
        return d


class RelationshipType(Enum):
    """Enumeration of SPDX relationship types."""

    DESCRIBES = auto()
    DEPENDS_ON = auto()
    OPTIONAL_DEPENDENCY_OF = auto()

    def __str__(self) -> str:
        return self.name


class Relationship():
    """Represents a relationship between SPDX elements."""

    def __init__(
        self,
        spdx_element_id: str,
        relationship_type: RelationshipType,
        related_spdx_element_id: Union[str, NoneValue, NoAssertionValue],
        comment: Optional[str] = None,
    ) -> None:
        self.spdx_element_id = spdx_element_id
        self.relationship_type = relationship_type
        self.related_spdx_element_id = related_spdx_element_id
        self.comment = comment

    def to_dict(self):
        d = {
            "spdxElementId": self.spdx_element_id,
            "relationshipType": str(self.relationship_type),
            "relatedSpdxElement": str(self.related_spdx_element_id),
        }
        if self.comment:
            d["comment"] = self.comment
        return d


class Document():
    """Represents an SPDX document."""

    def __init__(
        self,
        creation_info: CreationInfo,
        packages: Optional[List[Package]] = None,
        relationships: Optional[List[Relationship]] = None,
    ) -> None:
        self.creation_info = creation_info
        self.packages = packages or []
        self.relationships = relationships or []

    def to_dict(self):
        d = self.creation_info.to_dict()
        for package in self.packages:
            d.setdefault("packages", []).append(package.to_dict())
        for relationship in self.relationships:
            d.setdefault("relationships", []).append(relationship.to_dict())
        return d
