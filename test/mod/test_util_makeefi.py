#
# Tests for the 'osbuild.util.makeefi' module
#
import contextlib
import os
import random
import subprocess as sp

import pytest

from osbuild.util.makeefi import mkefiboot


class TestLoopClient:
    """
    Implements only the device() context manager method from the
    remoteloop.LoopClient class that is used in mkefiboot().
    """

    @contextlib.contextmanager
    def device(self, path):
        output = sp.check_output(["losetup", "--find", "--show", path])
        device = output.strip()
        yield device
        sp.check_call(["losetup", "--detach", device])


@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
def test_mkefiboot(tmp_path):

    efidir = tmp_path / "efidir"
    efidir.mkdir()

    efi_files = []

    for fnum in range(99):
        name = f"rand_file_{fnum:02d}.bin"
        rand_file = efidir / name
        filesize = random.randrange(100, 500)
        rand_file.write_bytes(random.getrandbits(filesize * 8).to_bytes(filesize, 'little'))
        efi_files.append(rand_file.relative_to(efidir))

    output_efiboot_img = tmp_path / "efiboot.img"

    loop_client = TestLoopClient()
    mkefiboot(efidir, output_efiboot_img, loop_client)

    # Verify the image size is aligned to a 512 byte boundary
    assert output_efiboot_img.stat().st_size % 512 == 0

    # Verify the image contains the expected files under /EFI/
    mountpoint = tmp_path / "mnt"
    mountpoint.mkdir()

    with loop_client.device(output_efiboot_img) as loopdev:
        try:
            sp.check_call(["mount", "-o", "utf8", loopdev, mountpoint])
            files_in_image = []
            for f in (mountpoint / "EFI").iterdir():
                files_in_image.append(f.relative_to(mountpoint / "EFI"))
        finally:
            sp.check_call(["umount", loopdev])

    assert sorted(files_in_image) == sorted(efi_files)
