#
# Runtime / Integration Tests for ostree pipelines
#

import os
import tempfile
import pytest

from .. import test


@pytest.fixture(name="tmpdir", scope="module")
def tmpdir_fixture():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture(name="osb", scope="module")
def osbuild_fixture():
    with test.OSBuild() as osb:
        yield osb


@pytest.fixture(name="testdata", scope="module")
def testdata_fixture():
    return test.TestBase.locate_test_data()


@pytest.mark.skipif(not test.TestBase.have_test_data(), reason="no test-data access")
@pytest.mark.skipif(not test.TestBase.can_bind_mount(), reason="root-only")
def test_ostree_container(osb, tmpdir, testdata):

    # Build a container
    manifest = os.path.join(testdata,
                            "manifests/fedora-ostree-container.json")
    osb.compile_file(manifest,
                     output_dir=tmpdir,
                     checkpoints=["build", "ostree-tree", "ostree-commit"],
                     exports=["container"])

    oci_archive = os.path.join(tmpdir, "container", "fedora-container.tar")
    assert os.path.exists(oci_archive)


@pytest.mark.skipif(not test.TestBase.have_test_data(), reason="no test-data access")
@pytest.mark.skipif(not test.TestBase.can_bind_mount(), reason="root-only")
def test_ostree_bootiso(osb, tmpdir, testdata):
    # build a bootable ISO
    manifest = os.path.join(testdata,
                            "manifests/fedora-ostree-bootiso.json")
    osb.compile_file(manifest,
                     output_dir=tmpdir,
                     checkpoints=["build", "ostree-tree", "ostree-commit"],
                     exports=["bootiso"])

    bootiso = os.path.join(tmpdir, "bootiso", "fedora-ostree-boot.iso")
    assert os.path.exists(bootiso)


@pytest.mark.skipif(not test.TestBase.have_test_data(), reason="no test-data access")
@pytest.mark.skipif(not test.TestBase.can_bind_mount(), reason="root-only")
def test_ostree_image(osb, tmpdir, testdata):
    # build a qemu image
    manifest = os.path.join(testdata,
                            "manifests/fedora-ostree-image.json")
    osb.compile_file(manifest,
                     output_dir=tmpdir,
                     checkpoints=["build", "ostree-tree", "ostree-commit"],
                     exports=["qcow2"])

    bootiso = os.path.join(tmpdir, "qcow2", "disk.qcow2")
    assert os.path.exists(bootiso)
