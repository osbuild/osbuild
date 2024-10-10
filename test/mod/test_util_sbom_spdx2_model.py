import json
from datetime import datetime

import fastjsonschema
import pytest

from osbuild.util.sbom.spdx2.model import (
    CATEGORY_TO_REPOSITORY_TYPE,
    Checksum,
    ChecksumAlgorithm,
    CreationInfo,
    Creator,
    CreatorType,
    Document,
    EntityWithSpdxId,
    ExternalPackageRef,
    ExternalPackageRefCategory,
    NoAssertionValue,
    NoneValue,
    Package,
    Relationship,
    RelationshipType,
    datetime_to_iso8601,
)

zoneinfo = pytest.importorskip("zoneinfo")


def test_creator_type_str():
    assert str(CreatorType.PERSON) == "Person"
    assert str(CreatorType.ORGANIZATION) == "Organization"
    assert str(CreatorType.TOOL) == "Tool"


@pytest.mark.parametrize("test_object,expected_str", (
    (
        Creator(CreatorType.TOOL, "Sample-Tool-123"),
        "Tool: Sample-Tool-123"
    ),
    (
        Creator(CreatorType.ORGANIZATION, "Sample Organization"),
        "Organization: Sample Organization"
    ),
    (
        Creator(CreatorType.ORGANIZATION, "Sample Organization", "email@example.com"),
        "Organization: Sample Organization (email@example.com)"
    ),
    (
        Creator(CreatorType.PERSON, "John Foo"),
        "Person: John Foo"
    ),
    (
        Creator(CreatorType.PERSON, "John Foo", "email@example.com"),
        "Person: John Foo (email@example.com)"
    )
))
def test_creator_str(test_object, expected_str):
    assert str(test_object) == expected_str


@pytest.mark.parametrize("test_spdx_id,error", (
    ("SPDXRef-DOCUMENT", False),
    ("SPDXRef-package-1.2.3", False),
    ("SPDXRef-package-1.2.3-0ec6114d-8d46-4553-a310-4df502c29082", False),
    ("", True),
    ("SPDXRef-", True),
    ("SPDxRef-DOCUMENT", True),
    ("SPDXRef-createrepo_c-1.2.3-1", True)
))
def test_entity_with_spdx_id(test_spdx_id, error):
    if error:
        with pytest.raises(ValueError):
            _ = EntityWithSpdxId(test_spdx_id)
    else:
        _ = EntityWithSpdxId(test_spdx_id)


@pytest.mark.parametrize("test_date,expected_str", (
    (datetime(2024, 11, 15, 14, 33, tzinfo=zoneinfo.ZoneInfo("UTC")), "2024-11-15T14:33:00Z"),
    (datetime(2024, 11, 15, 14, 33, 59, tzinfo=zoneinfo.ZoneInfo("UTC")), "2024-11-15T14:33:59Z"),
    (datetime(2024, 11, 15, 14, 33, 59, 123456, tzinfo=zoneinfo.ZoneInfo("UTC")), "2024-11-15T14:33:59Z"),
    (datetime(2024, 11, 15, 14, 33, tzinfo=zoneinfo.ZoneInfo("Europe/Prague")), "2024-11-15T13:33:00Z"),
    (datetime(2024, 11, 15, 14, 33, 59, tzinfo=zoneinfo.ZoneInfo("Europe/Prague")), "2024-11-15T13:33:59Z")
))
def test_datetime_to_iso8601(test_date, expected_str):
    assert datetime_to_iso8601(test_date) == expected_str


@pytest.mark.parametrize("test_case", (
    {
        "instance_args": {
            "spdx_version": "SPDX-2.3",
            "spdx_id": "SPDXRef-DOCUMENT",
            "name": "Sample-Document",
            "document_namespace": "https://example.com",
            "creators": [Creator(CreatorType.TOOL, "Sample-Tool-123")],
            "created": datetime(2024, 11, 15, 14, 33, 59, tzinfo=zoneinfo.ZoneInfo("Europe/Prague")),
            "data_license": "Public Domain"
        },
        "expected": {
            "spdxVersion": "SPDX-2.3",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "Sample-Document",
            "dataLicense": "Public Domain",
            "documentNamespace": "https://example.com",
            "creationInfo": {
                "created": "2024-11-15T13:33:59Z",
                "creators": [
                    "Tool: Sample-Tool-123"
                ]
            }
        },
    },
    {
        "instance_args": {
            "spdx_version": "SPDX-2.3",
            "spdx_id": "SPDXRef-DOCUMENT",
            "name": "Sample-Document",
            "document_namespace": "https://example.com",
            "creators": [Creator(CreatorType.TOOL, "Sample-Tool-123")],
            "created": datetime(2024, 11, 15, 14, 33, 59, tzinfo=zoneinfo.ZoneInfo("Europe/Prague")),
        },
        "expected": {
            "spdxVersion": "SPDX-2.3",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "Sample-Document",
            "dataLicense": "CC0-1.0",
            "documentNamespace": "https://example.com",
            "creationInfo": {
                "created": "2024-11-15T13:33:59Z",
                "creators": [
                    "Tool: Sample-Tool-123"
                ]
            }
        }
    },
    {
        "instance_args": {
            "spdx_version": "SPDX-2.3",
            "spdx_id": "DOCUMENT",
            "name": "Sample-Document",
            "document_namespace": "https://example.com",
            "creators": [Creator(CreatorType.TOOL, "Sample-Tool-123")],
            "created": datetime(2024, 11, 15, 14, 33, 59, tzinfo=zoneinfo.ZoneInfo("Europe/Prague")),
        },
        "error": True
    },
    {
        "instance_args": {
            "spdx_version": "SPDX-2.3",
            "spdx_id": "SPDXRef-YOLO",
            "name": "Sample-Document",
            "document_namespace": "https://example.com",
            "creators": [Creator(CreatorType.TOOL, "Sample-Tool-123")],
            "created": datetime(2024, 11, 15, 14, 33, 59, tzinfo=zoneinfo.ZoneInfo("Europe/Prague")),
        },
        "error": True
    }
))
def test_creation_info_to_dict(test_case):
    if test_case.get("error", False):
        with pytest.raises(ValueError):
            CreationInfo(**test_case["instance_args"])
    else:
        ci = CreationInfo(**test_case["instance_args"])
        assert ci.to_dict() == test_case["expected"]


def test_no_assertion_value_str():
    assert str(NoAssertionValue()) == "NOASSERTION"


def test_none_value_str():
    assert str(NoneValue()) == "NONE"


def test_external_package_ref_category_str():
    assert str(ExternalPackageRefCategory.SECURITY) == "SECURITY"
    assert str(ExternalPackageRefCategory.PACKAGE_MANAGER) == "PACKAGE-MANAGER"
    assert str(ExternalPackageRefCategory.PERSISTENT_ID) == "PERSISTENT-ID"
    assert str(ExternalPackageRefCategory.OTHER) == "OTHER"


def test_external_package_ref_cat_type_combinations():
    for category, types in CATEGORY_TO_REPOSITORY_TYPE.items():
        if category == ExternalPackageRefCategory.OTHER:
            _ = ExternalPackageRef(category, "made-up", "https://example.com")
            _ = ExternalPackageRef(category, "yolo-type", "https://example.com")
            continue

        for ref_type in types:
            _ = ExternalPackageRef(category, ref_type, "https://example.com")

        with pytest.raises(ValueError):
            _ = ExternalPackageRef(category, "made-up", "https://example.com")


def test_external_package_ref_to_dict():
    ref = ExternalPackageRef(ExternalPackageRefCategory.PACKAGE_MANAGER, "purl", "https://example.com")
    assert ref.to_dict() == {
        "referenceCategory": "PACKAGE-MANAGER",
        "referenceType": "purl",
        "referenceLocator": "https://example.com"
    }


def test_checksum_algorithm_str():
    assert str(ChecksumAlgorithm.SHA1) == "SHA1"
    assert str(ChecksumAlgorithm.SHA224) == "SHA224"
    assert str(ChecksumAlgorithm.SHA256) == "SHA256"
    assert str(ChecksumAlgorithm.SHA384) == "SHA384"
    assert str(ChecksumAlgorithm.SHA512) == "SHA512"
    assert str(ChecksumAlgorithm.SHA3_256) == "SHA3-256"
    assert str(ChecksumAlgorithm.SHA3_384) == "SHA3-384"
    assert str(ChecksumAlgorithm.SHA3_512) == "SHA3-512"
    assert str(ChecksumAlgorithm.BLAKE2b_256) == "BLAKE2b-256"
    assert str(ChecksumAlgorithm.BLAKE2b_384) == "BLAKE2b-384"
    assert str(ChecksumAlgorithm.BLAKE2b_512) == "BLAKE2b-512"
    assert str(ChecksumAlgorithm.BLAKE3) == "BLAKE3"
    assert str(ChecksumAlgorithm.MD2) == "MD2"
    assert str(ChecksumAlgorithm.MD4) == "MD4"
    assert str(ChecksumAlgorithm.MD5) == "MD5"
    assert str(ChecksumAlgorithm.MD6) == "MD6"
    assert str(ChecksumAlgorithm.ADLER32) == "ADLER32"


def test_checksum_to_dict():
    assert Checksum(ChecksumAlgorithm.SHA1, "123456").to_dict() == {
        "algorithm": "SHA1",
        "checksumValue": "123456"
    }


@pytest.mark.parametrize("test_case", (
    {
        "instance_args": {
            "spdx_id": "SPDXRef-package-1.2.3",
            "name": "package",
            "download_location": "https://example.org/package-1.2.3.rpm"
        },
        "expected": {
            "SPDXID": "SPDXRef-package-1.2.3",
            "name": "package",
            "downloadLocation": "https://example.org/package-1.2.3.rpm"
        }
    },
    {
        "instance_args": {
            "spdx_id": "SPDXRef-package-1.2.3",
            "name": "package",
            "download_location": NoAssertionValue(),
            "files_analyzed": True
        },
        "expected": {
            "SPDXID": "SPDXRef-package-1.2.3",
            "name": "package",
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": True
        }
    },
    {
        "instance_args": {
            "spdx_id": "SPDXRef-package-1.2.3",
            "name": "package",
            "download_location": NoneValue(),
            "files_analyzed": False,
            "checksums": [
                Checksum(ChecksumAlgorithm.SHA256, "123456")
            ],
            "version": "1.2.3",
            "homepage": "https://example.org/package",
            "source_info": "https://example.org/package-1.2.3.src.rpm",
            "license_declared": "MIT",
            "summary": "A sample package",
            "description": "A sample package description",
            "external_references": [
                ExternalPackageRef(
                    ExternalPackageRefCategory.PACKAGE_MANAGER,
                    "purl",
                    "pkg:rpm:/example/package@1.2.3-1?arch=x86_64"
                )
            ],
            "built_date": datetime(2024, 11, 15, 14, 33, 59, tzinfo=zoneinfo.ZoneInfo("Europe/Prague"))
        },
        "expected": {
            "SPDXID": "SPDXRef-package-1.2.3",
            "name": "package",
            "downloadLocation": "NONE",
            "filesAnalyzed": False,
            "checksums": [
                {
                    "algorithm": "SHA256",
                    "checksumValue": "123456"
                }
            ],
            "versionInfo": "1.2.3",
            "homepage": "https://example.org/package",
            "sourceInfo": "https://example.org/package-1.2.3.src.rpm",
            "licenseDeclared": "MIT",
            "summary": "A sample package",
            "description": "A sample package description",
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": "pkg:rpm:/example/package@1.2.3-1?arch=x86_64"
                }
            ],
            "builtDate": "2024-11-15T13:33:59Z"
        }
    }
))
def test_package_to_dict(test_case):
    p = Package(**test_case["instance_args"])
    assert p.to_dict() == test_case["expected"]


def test_relationship_type_str():
    assert str(RelationshipType.DESCRIBES) == "DESCRIBES"
    assert str(RelationshipType.DEPENDS_ON) == "DEPENDS_ON"
    assert str(RelationshipType.OPTIONAL_DEPENDENCY_OF) == "OPTIONAL_DEPENDENCY_OF"


@pytest.mark.parametrize("test_case", (
    {
        "instance_args": {
            "spdx_element_id": "SPDXRef-packageA-1.2.3",
            "relationship_type": RelationshipType.DEPENDS_ON,
            "related_spdx_element_id": "SPDXRef-packageB-3.2.1"
        },
        "expected": {
            "spdxElementId": "SPDXRef-packageA-1.2.3",
            "relationshipType": "DEPENDS_ON",
            "relatedSpdxElement": "SPDXRef-packageB-3.2.1"
        }
    },
    {
        "instance_args": {
            "spdx_element_id": "SPDXRef-DOCUMENT",
            "relationship_type": RelationshipType.DESCRIBES,
            "related_spdx_element_id": "SPDXRef-packageB-3.2.1",
            "comment": "This document describes package B"
        },
        "expected": {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": "SPDXRef-packageB-3.2.1",
            "comment": "This document describes package B"
        }
    },
))
def test_relationship_to_dict(test_case):
    r = Relationship(**test_case["instance_args"])
    assert r.to_dict() == test_case["expected"]


@pytest.mark.parametrize("test_case", (
    {
        "instance_args": {
            "creation_info": CreationInfo(
                "SPDX-2.3",
                "SPDXRef-DOCUMENT",
                "Sample-Document",
                "https://example.com",
                [Creator(CreatorType.TOOL, "Sample-Tool-123")],
                datetime(2024, 11, 15, 14, 33, 59, tzinfo=zoneinfo.ZoneInfo("Europe/Prague")),
                "Public Domain"
            )
        },
        "expected": {
            "spdxVersion": "SPDX-2.3",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "Sample-Document",
            "dataLicense": "Public Domain",
            "documentNamespace": "https://example.com",
            "creationInfo": {
                "created": "2024-11-15T13:33:59Z",
                "creators": [
                    "Tool: Sample-Tool-123"
                ]
            }
        }
    },
    {
        "instance_args": {
            "creation_info": CreationInfo(
                "SPDX-2.3",
                "SPDXRef-DOCUMENT",
                "Sample-Document",
                "https://example.com",
                [Creator(CreatorType.TOOL, "Sample-Tool-123")],
                datetime(2024, 11, 15, 14, 33, 59, tzinfo=zoneinfo.ZoneInfo("Europe/Prague")),
                "Public Domain"
            ),
            "packages": [
                Package(
                    "SPDXRef-packageA-1.2.3",
                    "package",
                    "https://example.org/packageA-1.2.3.rpm"
                ),
                Package(
                    "SPDXRef-packageB-3.2.1",
                    "package",
                    "https://example.org/packageB-3.2.1.rpm"
                ),
            ],
            "relationships": [
                Relationship(
                    "SPDXRef-DOCUMENT",
                    RelationshipType.DESCRIBES,
                    "SPDXRef-packageA-1.2.3"
                ),
                Relationship(
                    "SPDXRef-DOCUMENT",
                    RelationshipType.DESCRIBES,
                    "SPDXRef-packageB-3.2.1"
                ),
                Relationship(
                    "SPDXRef-packageA-1.2.3",
                    RelationshipType.DEPENDS_ON,
                    "SPDXRef-packageB-3.2.1"
                )
            ]
        },
        "expected": {
            "spdxVersion": "SPDX-2.3",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "Sample-Document",
            "dataLicense": "Public Domain",
            "documentNamespace": "https://example.com",
            "creationInfo": {
                "created": "2024-11-15T13:33:59Z",
                "creators": [
                    "Tool: Sample-Tool-123"
                ]
            },
            "packages": [
                {
                    "SPDXID": "SPDXRef-packageA-1.2.3",
                    "name": "package",
                    "downloadLocation": "https://example.org/packageA-1.2.3.rpm"
                },
                {
                    "SPDXID": "SPDXRef-packageB-3.2.1",
                    "name": "package",
                    "downloadLocation": "https://example.org/packageB-3.2.1.rpm"
                }
            ],
            "relationships": [
                {
                    "spdxElementId": "SPDXRef-DOCUMENT",
                    "relationshipType": "DESCRIBES",
                    "relatedSpdxElement": "SPDXRef-packageA-1.2.3"
                },
                {
                    "spdxElementId": "SPDXRef-DOCUMENT",
                    "relationshipType": "DESCRIBES",
                    "relatedSpdxElement": "SPDXRef-packageB-3.2.1"
                },
                {
                    "spdxElementId": "SPDXRef-packageA-1.2.3",
                    "relationshipType": "DEPENDS_ON",
                    "relatedSpdxElement": "SPDXRef-packageB-3.2.1"
                }
            ]
        }
    }
))
def test_document_to_dict(test_case):
    d = Document(**test_case["instance_args"])
    assert d.to_dict() == test_case["expected"]

    spdx_2_3_1_schema_file = './test/data/spdx/spdx-schema-v2.3.1.json'
    with open(spdx_2_3_1_schema_file, encoding="utf-8") as f:
        spdx_schema = json.load(f)

    spdx_validator = fastjsonschema.compile(spdx_schema)
    spdx_validator(d.to_dict())
