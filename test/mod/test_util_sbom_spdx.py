import os

import pytest

import osbuild
from osbuild.util.sbom.spdx import create_spdx2_document, sbom_pkgset_to_spdx2_doc, spdx2_checksum_algorithm
from osbuild.util.sbom.spdx2.model import CreatorType, ExternalPackageRefCategory, RelationshipType

testutil_dnf4 = pytest.importorskip("osbuild.testutil.dnf4")
bom_dnf = pytest.importorskip("osbuild.util.sbom.dnf")


def test_create_spdx2_document():
    doc1 = create_spdx2_document()

    assert doc1.creation_info.spdx_version == "SPDX-2.3"
    assert doc1.creation_info.spdx_id == "SPDXRef-DOCUMENT"
    assert doc1.creation_info.name == f"sbom-by-osbuild-{osbuild.__version__}"
    assert doc1.creation_info.data_license == "CC0-1.0"
    assert doc1.creation_info.document_namespace.startswith("https://osbuild.org/spdxdocs/sbom-by-osbuild-")
    assert len(doc1.creation_info.creators) == 1
    assert doc1.creation_info.creators[0].creator_type == CreatorType.TOOL
    assert doc1.creation_info.creators[0].name == f"osbuild-{osbuild.__version__}"
    assert doc1.creation_info.created

    doc2 = create_spdx2_document()
    assert doc1.creation_info.document_namespace != doc2.creation_info.document_namespace
    assert doc1.creation_info.created != doc2.creation_info.created

    doc1_dict = doc1.to_dict()
    doc2_dict = doc2.to_dict()
    del doc1_dict["creationInfo"]["created"]
    del doc2_dict["creationInfo"]["created"]
    del doc1_dict["documentNamespace"]
    del doc2_dict["documentNamespace"]
    assert doc1_dict == doc2_dict


def test_sbom_pkgset_to_spdx2_doc():
    dnf_pkgset = testutil_dnf4.depsolve_pkgset([os.path.abspath("./test/data/testrepos/baseos")], ["bash"])
    bom_pkgset = bom_dnf.dnf_pkgset_to_sbom_pkgset(dnf_pkgset)
    doc = sbom_pkgset_to_spdx2_doc(bom_pkgset)

    assert len(doc.packages) == len(bom_pkgset)
    for spdx_pkg, bom_pkg in zip(doc.packages, bom_pkgset):
        assert spdx_pkg.spdx_id == f"SPDXRef-{bom_pkg.uuid()}"
        assert spdx_pkg.name == bom_pkg.name
        assert spdx_pkg.version == bom_pkg.version
        assert not spdx_pkg.files_analyzed
        assert spdx_pkg.license_declared == bom_pkg.license_declared
        assert spdx_pkg.download_location == bom_pkg.download_url
        assert spdx_pkg.homepage == bom_pkg.homepage
        assert spdx_pkg.summary == bom_pkg.summary
        assert spdx_pkg.description == bom_pkg.description
        assert spdx_pkg.source_info == bom_pkg.source_info()
        assert spdx_pkg.built_date == bom_pkg.build_date

        assert len(spdx_pkg.checksums) == 1
        assert spdx_pkg.checksums[0].algorithm == spdx2_checksum_algorithm(list(bom_pkg.checksums.keys())[0])
        assert spdx_pkg.checksums[0].value == list(bom_pkg.checksums.values())[0]

        assert len(spdx_pkg.external_references) == 1
        assert spdx_pkg.external_references[0].category == ExternalPackageRefCategory.PACKAGE_MANAGER
        assert spdx_pkg.external_references[0].reference_type == "purl"
        assert spdx_pkg.external_references[0].locator == bom_pkg.purl()

    assert len([rel for rel in doc.relationships if rel.relationship_type ==
                RelationshipType.DESCRIBES]) == len(bom_pkgset)

    deps_count = sum(len(bom_pkg.depends_on) for bom_pkg in bom_pkgset)
    assert len([rel for rel in doc.relationships if rel.relationship_type ==
                RelationshipType.DEPENDS_ON]) == deps_count

    optional_deps_count = sum(len(bom_pkg.optional_depends_on) for bom_pkg in bom_pkgset)
    assert len([rel for rel in doc.relationships if rel.relationship_type ==
                RelationshipType.OPTIONAL_DEPENDENCY_OF]) == optional_deps_count
