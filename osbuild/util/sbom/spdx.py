from datetime import datetime
from typing import List, Union
from uuid import uuid4

import osbuild
import osbuild.util.sbom.model as sbom_model
import osbuild.util.sbom.spdx2 as spdx2


def spdx2_checksum_algorithm(algorithm: sbom_model.ChecksumAlgorithm) -> spdx2.ChecksumAlgorithm:
    if algorithm == sbom_model.ChecksumAlgorithm.SHA1:
        return spdx2.ChecksumAlgorithm.SHA1
    if algorithm == sbom_model.ChecksumAlgorithm.SHA224:
        return spdx2.ChecksumAlgorithm.SHA224
    if algorithm == sbom_model.ChecksumAlgorithm.SHA256:
        return spdx2.ChecksumAlgorithm.SHA256
    if algorithm == sbom_model.ChecksumAlgorithm.SHA384:
        return spdx2.ChecksumAlgorithm.SHA384
    if algorithm == sbom_model.ChecksumAlgorithm.SHA512:
        return spdx2.ChecksumAlgorithm.SHA512
    if algorithm == sbom_model.ChecksumAlgorithm.MD5:
        return spdx2.ChecksumAlgorithm.MD5
    raise ValueError(f"Unknown checksum algorithm: {algorithm}")


def create_spdx2_document():
    tool = f"osbuild-{osbuild.__version__}"
    doc_name = f"sbom-by-{tool}"

    ci = spdx2.CreationInfo(
        spdx_version="SPDX-2.3",
        spdx_id="SPDXRef-DOCUMENT",
        name=doc_name,
        data_license="CC0-1.0",
        document_namespace=f"https://osbuild.org/spdxdocs/{doc_name}-{uuid4()}",
        creators=[spdx2.Creator(spdx2.CreatorType.TOOL, tool)],
        created=datetime.now(),
    )
    doc = spdx2.Document(ci)

    return doc


def bom_pkgset_to_spdx2_doc(pkgset: List[sbom_model.BasePackage]) -> spdx2.Document:
    doc = create_spdx2_document()
    relationships = []

    for pkg in pkgset:

        download_location: Union[str, spdx2.NoAssertionValue] = spdx2.NoAssertionValue()
        if pkg.download_url:
            download_location = pkg.download_url

        p = spdx2.Package(
            spdx_id=f"SPDXRef-{pkg.uuid()}",
            name=pkg.name,
            download_location=download_location,
            version=pkg.version,
            files_analyzed=False,
            license_declared=pkg.license_declared,
            external_references=[
                spdx2.ExternalPackageRef(
                    category=spdx2.ExternalPackageRefCategory.PACKAGE_MANAGER,
                    reference_type="purl",
                    locator=pkg.purl(),
                )
            ]
        )

        if pkg.homepage:
            p.homepage = pkg.homepage

        if pkg.summary:
            p.summary = pkg.summary

        if pkg.description:
            p.description = pkg.description

        if pkg.source_info():
            p.source_info = pkg.source_info()

        for hash_type, hash_value in pkg.checksums.items():
            p.checksums.append(
                spdx2.Checksum(
                    algorithm=spdx2_checksum_algorithm(hash_type),
                    value=hash_value,
                )
            )

        if pkg.build_date:
            p.built_date = pkg.build_date

        doc.packages.append(p)

        relationships.append(
            spdx2.Relationship(
                spdx_element_id=doc.creation_info.spdx_id,
                relationship_type=spdx2.RelationshipType.DESCRIBES,
                related_spdx_element_id=p.spdx_id,
            )
        )

        for dep in sorted(pkg.depends_on, key=lambda x: x.uuid()):
            relationships.append(
                spdx2.Relationship(
                    spdx_element_id=p.spdx_id,
                    relationship_type=spdx2.RelationshipType.DEPENDS_ON,
                    related_spdx_element_id=f"SPDXRef-{dep.uuid()}",
                )
            )

        for optional_dep in sorted(pkg.optional_depends_on, key=lambda x: x.uuid()):
            relationships.append(
                spdx2.Relationship(
                    spdx_element_id=f"SPDXRef-{optional_dep.uuid()}",
                    relationship_type=spdx2.RelationshipType.OPTIONAL_DEPENDENCY_OF,
                    related_spdx_element_id=p.spdx_id,
                )
            )

    doc.relationships = relationships

    return doc
