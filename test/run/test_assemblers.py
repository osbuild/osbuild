#
# Runtime tests for the individual assemblers.
#

import contextlib
import hashlib
import json
import os
import subprocess
import tempfile

import pytest

from osbuild import loop

from .. import test

MEBIBYTE = 1024 * 1024


@pytest.fixture(name="osbuild")
def osbuild_fixture():
    store = os.getenv("OSBUILD_TEST_STORE")
    osb = test.OSBuild(cache_from=store)
    yield osb


def assertImageFile(filename, fmt, expected_size):
    info = json.loads(subprocess.check_output(["qemu-img", "info", "--output", "json", filename]))
    assert info["format"] == fmt
    assert info["virtual-size"] == expected_size


def assertFilesystem(device, uuid, fstype, tree):
    output = subprocess.check_output(["blkid", "--output", "export", device], encoding="utf8")
    blkid = dict(line.split("=") for line in output.strip().split("\n"))
    assert blkid["UUID"] == uuid
    assert blkid["TYPE"] == fstype

    with mount(device) as target_tree:
        diff = test.TestBase.tree_diff(tree, target_tree)
        if fstype == 'ext4':
            added_files = ["/lost+found"]
        else:
            added_files = []
        assert diff["added_files"] == added_files
        assert diff["deleted_files"] == []
        assert diff["differences"] == {}


def assertGRUB2(device, l1hash, l2hash, size):
    m1 = hashlib.sha256()
    m2 = hashlib.sha256()
    with open(device, "rb") as d:
        sectors = d.read(size)
    assert len(sectors) == size
    m1.update(sectors[:440])
    m2.update(sectors[512:size])
    assert m1.hexdigest() == l1hash
    assert m2.hexdigest() == l2hash


def assertPartitionTable(ptable, label, uuid, n_partitions, boot_partition=None):
    assert ptable["label"] == label
    assert ptable["id"][2:] == uuid[:8]
    assert len(ptable["partitions"]) == n_partitions

    if boot_partition:
        bootable = [p.get("bootable", False) for p in ptable["partitions"]]
        assert bootable.count(True) == 1
        assert bootable.index(True) + 1 == boot_partition


def read_partition_table(device):
    sfdisk = json.loads(subprocess.check_output(["sfdisk", "--json", device]))
    ptable = sfdisk["partitiontable"]
    assert ptable is not None
    return ptable


@pytest.mark.skipif(not test.TestBase.have_tree_diff(), reason="tree-diff missing")
@pytest.mark.skipif(not test.TestBase.have_test_data(), reason="no test-data access")
@pytest.mark.skipif(not test.TestBase.can_bind_mount(), reason="root-only")
@pytest.mark.parametrize("fs_type", ["ext4", "xfs", "btrfs"])
def test_rawfs(osbuild, fs_type):
    if not test.TestBase.has_filesystem_support(fs_type):
        pytest.skip(f"The {fs_type} was explicitly marked as unsupported on this platform.")
    options = {
        "filename": "image.raw",
        "root_fs_uuid": "016a1cda-5182-4ab3-bf97-426b00b74eb0",
        "size": 1024 * MEBIBYTE,
        "fs_type": fs_type,
    }
    with osbuild as osb:
        with run_assembler(osb, "org.osbuild.rawfs", options, "image.raw") as (tree, image):
            assertImageFile(image, "raw", options["size"])
            assertFilesystem(image, options["root_fs_uuid"], fs_type, tree)


@pytest.mark.skipif(not test.TestBase.have_tree_diff(), reason="tree-diff missing")
@pytest.mark.skipif(not test.TestBase.have_test_data(), reason="no test-data access")
@pytest.mark.skipif(not test.TestBase.can_bind_mount(), reason="root-only")
@pytest.mark.skipif(not test.TestBase.have_rpm_ostree(), reason="rpm-ostree missing")
def test_ostree(osbuild):
    with osbuild as osb:
        with open(os.path.join(test.TestBase.locate_test_data(),
                               "manifests/fedora-ostree-commit.json"),
                  encoding="utf8") as f:
            manifest = json.load(f)

        data = json.dumps(manifest)
        with tempfile.TemporaryDirectory(dir="/var/tmp") as output_dir:
            result = osb.compile(data, output_dir=output_dir, exports=["ostree-commit"])
            compose_file = os.path.join(output_dir, "ostree-commit", "compose.json")
            repo = os.path.join(output_dir, "ostree-commit", "repo")

            with open(compose_file, encoding="utf8") as f:
                compose = json.load(f)
            commit_id = compose["ostree-commit"]
            ref = compose["ref"]
            rpmostree_inputhash = compose["rpm-ostree-inputhash"]
            os_version = compose["ostree-version"]
            assert commit_id
            assert ref
            assert rpmostree_inputhash
            assert os_version
            assert "metadata" in result
            metadata = result["metadata"]
            commit = metadata["ostree-commit"]
            info = commit["org.osbuild.ostree.commit"]
            assert "compose" in info
            assert info["compose"] == compose

            md = subprocess.check_output(
                [
                    "ostree",
                    "show",
                    "--repo", repo,
                    "--print-metadata-key=rpmostree.inputhash",
                    commit_id
                ], encoding="utf8").strip()
            assert md == f"'{rpmostree_inputhash}'"

            md = subprocess.check_output(
                [
                    "ostree",
                    "show",
                    "--repo", repo,
                    "--print-metadata-key=version",
                    commit_id
                ], encoding="utf8").strip()
            assert md == f"'{os_version}'"


@pytest.mark.skipif(not test.TestBase.have_tree_diff(), reason="tree-diff missing")
@pytest.mark.skipif(not test.TestBase.have_test_data(), reason="no test-data access")
@pytest.mark.skipif(not test.TestBase.can_bind_mount(), reason="root-only")
@pytest.mark.parametrize("fmt,", ["raw", "raw.xz", "qcow2", "vmdk", "vdi"])
@pytest.mark.parametrize("fs_type", ["ext4", "xfs", "btrfs"])
def test_qemu(osbuild, fmt, fs_type):
    loctl = loop.LoopControl()
    with osbuild as osb:
        if not test.TestBase.has_filesystem_support(fs_type):
            pytest.skip(f"The {fs_type} was explicitly marked as unsupported on this platform.")
        options = {
            "format": fmt,
            "filename": f"image-{fs_type}.{fmt}",
            "ptuuid": "b2c09a39-db93-44c5-846a-81e06b1dc162",
            "root_fs_uuid": "aff010e9-df95-4f81-be6b-e22317251033",
            "size": 1024 * MEBIBYTE,
            "root_fs_type": fs_type,
        }
        with run_assembler(osb,
                           "org.osbuild.qemu",
                           options,
                           f"image-{fs_type}.{fmt}") as (tree, image):
            if fmt == "raw.xz":
                subprocess.run(["unxz", "--keep", "--force", image], check=True)
                image = image[:-3]
                fmt = "raw"
            assertImageFile(image, fmt, options["size"])
            with open_image(loctl, image, fmt) as (target, device):
                ptable = read_partition_table(device)
                assertPartitionTable(ptable,
                                     "dos",
                                     options["ptuuid"],
                                     1,
                                     boot_partition=1)
                if fs_type == "btrfs":
                    l2hash = "ba0ae9a8b907ad772359a6671de8af0a72def18566e9f2faf8843071777b8d0a"
                elif fs_type == "xfs":
                    l2hash = "9c7f4633df40fec6f31a4d595bc37a263e0a778f496fa314789e60cb9688f376"
                else:
                    l2hash = "f8272df4899991b20964a568607153ff71b5742bcbf1eeabb47145ccb554a81b"
                assertGRUB2(device,
                            "b8cea7475422d35cd6f85ad099fb4f921557fd1b25db62cd2a92709ace21cf0f",
                            l2hash,
                            1024 * 1024)

                p1 = ptable["partitions"][0]
                ssize = ptable.get("sectorsize", 512)
                start, size = p1["start"] * ssize, p1["size"] * ssize
                with loop_open(loctl, target, offset=start, size=size) as dev:
                    assertFilesystem(dev, options["root_fs_uuid"], fs_type, tree)


@pytest.mark.skipif(not test.TestBase.have_tree_diff(), reason="tree-diff missing")
@pytest.mark.skipif(not test.TestBase.have_test_data(), reason="no test-data access")
@pytest.mark.skipif(not test.TestBase.can_bind_mount(), reason="root-only")
@pytest.mark.parametrize(
    "filename,compression,expected_mimetypes",
    [("tree.tar.gz", None, ["application/x-tar"]),
     ("tree.tar.gz", "gzip", ["application/x-gzip", "application/gzip"])]
)
def test_tar(osbuild, filename, compression, expected_mimetypes):
    with osbuild as osb:
        options = {"filename": filename}
        if compression:
            options["compression"] = compression
        with run_assembler(osb,
                           "org.osbuild.tar",
                           options,
                           filename) as (tree, image):
            output = subprocess.check_output(["file", "--mime-type", image], encoding="utf8")
            _, mimetype = output.strip().split(": ")  # "filename: mimetype"
            assert mimetype in expected_mimetypes

            if compression:
                return

            # In the non-compression case, we verify the tree's content
            with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
                args = [
                    "tar",
                    "--numeric-owner",
                    "--selinux",
                    "--acls",
                    "--xattrs", "--xattrs-include", "*",
                    "-xaf", image,
                    "-C", tmp]
                subprocess.check_output(args, encoding="utf8")
                diff = test.TestBase.tree_diff(tree, tmp)
                assert diff["added_files"] == []
                assert diff["deleted_files"] == []
                assert diff["differences"] == {}


@contextlib.contextmanager
def loop_create_device(ctl, fd, offset=None, sizelimit=None):
    lo = None
    try:
        lo = ctl.loop_for_fd(fd,
                             offset=offset,
                             sizelimit=sizelimit,
                             autoclear=True,
                             lock=True)
        yield lo
    finally:
        if lo:
            lo.close()


@contextlib.contextmanager
def loop_open(ctl, image, *, offset=None, size=None):
    with open(image, "rb") as f:
        fd = f.fileno()
        with loop_create_device(ctl, fd, offset=offset, sizelimit=size) as lo:
            yield os.path.join("/dev", lo.devname)


@contextlib.contextmanager
def mount(device):
    with tempfile.TemporaryDirectory() as mountpoint:
        subprocess.run(["mount", "-o", "ro", device, mountpoint], check=True)
        try:
            yield mountpoint
        finally:
            subprocess.run(["umount", "--lazy", mountpoint], check=True)


@contextlib.contextmanager
def open_image(ctl, image, fmt):
    with tempfile.TemporaryDirectory() as tmp:
        if fmt != "raw":
            target = os.path.join(tmp, "image.raw")
            subprocess.run(["qemu-img", "convert", "-O", "raw", image, target],
                           check=True)
        else:
            target = image

        size = os.stat(target).st_size

        with loop_open(ctl, target, offset=0, size=size) as dev:
            yield target, dev


@contextlib.contextmanager
def run_assembler(osb, name, options, output_path):
    with open(os.path.join(test.TestBase.locate_test_data(),
                           "assemblers/manifest.json"),
              encoding="utf8") as f:
        manifest = json.load(f)
    manifest["pipeline"] = dict(
        manifest["pipeline"],
        assembler={"name": name, "options": options}
    )
    data = json.dumps(manifest)

    treeid = osb.treeid_from_manifest(data)
    assert treeid

    with tempfile.TemporaryDirectory(dir="/var/tmp") as output_dir:
        try:
            osb.compile(data, output_dir=output_dir, exports=["assembler", "tree"], checkpoints=["tree"])
            tree = os.path.join(output_dir, "tree")
            yield tree, os.path.join(output_dir, "assembler", output_path)
        finally:
            # re-use downloaded sources
            store = os.getenv("OSBUILD_TEST_STORE")
            if store:
                osb.copy_source_data(store, "org.osbuild.files")
