#!/usr/bin/python3

import contextlib
import os
import random
import subprocess as sp
import textwrap

import pytest

STAGE_NAME = "org.osbuild.coreos.live-artifacts.mono"


def test_get_os_features(tmp_path, stage_module):
    cfg_path = tmp_path / "usr/share/coreos-installer/example-config.yaml"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(textwrap.dedent("""\
    # Fedora CoreOS stream
    stream: name
    # Manually specify the image URL
    image-url: URL
    """))
    features = stage_module.get_os_features(tmp_path)
    assert {
        "installer-config": True,
        "installer-config-directives": {
            "stream": True,
            "image-url": True,
        },
        "live-initrd-network": True,
    } == features


@pytest.mark.parametrize("test_case", [
    {"orig_size": 0, "exp_size": 0},
    {"orig_size": 1, "exp_size": 4},
    {"orig_size": 2, "exp_size": 4},
    {"orig_size": 3, "exp_size": 4},
    {"orig_size": 4, "exp_size": 4},
    {"orig_size": 10938, "exp_size": 10940},
])
def test_align_initrd(tmp_path, stage_module, test_case):
    dest_file = tmp_path / "rootfs.img"
    dest_file.touch()

    os.truncate(dest_file, test_case["orig_size"])
    stage_module.align_initrd_for_uncompressed_append(dest_file.open(mode="ab"))
    assert dest_file.stat().st_size == test_case["exp_size"]

    with dest_file.open(mode="rb") as fp:
        fp.seek(test_case["orig_size"])
        padding_size = test_case["exp_size"] - test_case["orig_size"]
        padding = fp.read(padding_size)
    assert padding == b'\0' * padding_size


@pytest.mark.parametrize("test_case", [
    {"treefiles": ["file_b", "file_c", "file_1"], "compress": False},
    {"treefiles": ["file_b", "file_c", "root.squashfs", "file_1"], "compress": False},
    {"treefiles": ["file_b", "file_c", "file_1"], "compress": True},
    {"treefiles": ["file_b", "file_c", "root.squashfs", "file_1"], "compress": True},
])
def test_extend_initramfs(tmp_path, stage_module, test_case):
    img_path = tmp_path / "img"
    img_path.mkdir()
    dst = img_path / "dst.img"
    dst.touch()

    tree = tmp_path / "tree"
    tree.mkdir()
    treefiles = test_case["treefiles"]
    for fname in treefiles:
        (tree / fname).touch()

    stage_module.extend_initramfs(dst, tree, compress=test_case["compress"])

    if test_case["compress"]:
        # if we compressed, append .gz to the filename and let gunzip remove it when decompressing
        gz_name = str(dst) + ".gz"
        dst.rename(gz_name)
        sp.run(["gunzip", gz_name], check=True)

    output = sp.check_output(["cpio", "-i", "-t", "--file", dst])
    files_in_archive = output.decode().strip().split("\n")

    # check that all the elements match, regardless of order
    assert sorted(treefiles) == sorted(files_in_archive)
    if "root.squashfs" in treefiles:
        # root.squashfs must be first
        assert files_in_archive[0] == "root.squashfs"


def test_make_stream_hash(tmp_path, stage_module):
    src = tmp_path / "src"
    dst = tmp_path / "dst"

    with src.open(mode="wb") as src_file:
        # repeat enough times to require multiple buffers (bufsize == 2097152)
        src_file.write(b"TNdUoOTJgTAfeNYl9anmDpo8CxphoMaAoEESZWdwj45RZXNTHv7Fwsj5" * 100_000)

    stage_module.make_stream_hash(src, dst)
    with dst.open("r") as dst_file:
        stream_hash = dst_file.read()

    hashes = [
        "6f50ae3331d2d010465b42292e82e53dcc24548ef317eee80e71f657f56995d3",
        "d4170e95e324afa6b687a8cb45144e1edf75e3ac6b2c63e12dc31884b0bbfd01",
        "2f3599a36686b38dea4937c8c2dccd00574d03e0cba07e03e791f07c8f06bff1",
    ]
    assert stream_hash.strip().split("\n") == [
        "stream-hash sha256 2097152",
        *hashes,
    ]


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
def test_make_efi_bootfile(tmp_path, stage_module):

    tar_files_path = tmp_path / "tar_files"
    tar_files_path.mkdir()

    tar_files = []

    for fnum in range(99):
        name = f"rand_file_{fnum:02d}.bin"
        rand_file = tar_files_path / name
        filesize = random.randrange(100, 500)
        rand_file.write_bytes(random.getrandbits(filesize * 8).to_bytes(filesize, 'little'))
        tar_files.append(rand_file.relative_to(tar_files_path))

    input_tarball = tmp_path / "files.tar"
    sp.check_call(["tar", "-C", tar_files_path, "-cf", input_tarball, "."])

    output_efiboot_img = tmp_path / "efiboot.img"

    class TestLoopClient:
        """
        Implements only the device() context manager method from the remoteloop.LoopClient class that is used in the
        make_efi_bootfile() function.
        """

        @contextlib.contextmanager
        def device(self, path):
            output = sp.check_output(["losetup", "--find", "--show", path])
            device = output.strip()
            yield device
            sp.check_call(["losetup", "--detach", device])

    mountpoint = tmp_path / "mnt"
    mountpoint.mkdir()
    loop_client = TestLoopClient()
    stage_module.make_efi_bootfile(loop_client, input_tarball, output_efiboot_img)

    with loop_client.device(output_efiboot_img) as loopdev:
        try:
            sp.check_call(["mount", "-o", "utf8", loopdev, mountpoint])
            files_in_image = []
            for f in mountpoint.iterdir():
                files_in_image.append(f.relative_to(mountpoint))
        finally:
            sp.check_call(["umount", loopdev])

    assert sorted(files_in_image) == sorted(tar_files)
