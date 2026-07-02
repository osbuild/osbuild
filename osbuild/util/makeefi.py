"""EFI boot image utilities

Functions for building EFI boot directory layouts and
FAT filesystem images suitable for ISO / removable-media boot.
"""
import glob
import os
import shutil
import subprocess
import tarfile
import tempfile

from osbuild.util.path import ensure_glob


# This function finds the source EFI paths to copy from /usr/ to the EFI/
# directory. Historically this was just the usr/lib/bootupd/updates/EFI/
# directory (populated by bootupd), but as part of BootLoaderUpdatesPhase1 [1]
# the shim and grub packages started delivering files in
# /usr/lib/efi/(grub|shim)/<version>/EFI/ directly. Lets prefer the
# new paths and fallback to the legacy path if those don't exist.
#
# [1] https://fedoraproject.org/wiki/Changes/BootLoaderUpdatesPhase1
def find_efi_source_paths(tree):
    if glob.glob(os.path.join(tree, 'usr/lib/efi/*/*/EFI')):
        # BootLoaderUpdatesPhase1 has been implemented and we should
        # be able to pick up files from usr/lib/efi/(grub|shim)/<version>/EFI/
        # Let's ensure there's only 2 dirs that match (i.e. one for grub
        # one for shim) and return that list.
        return ensure_glob(os.path.join(tree, 'usr/lib/efi/*/*/EFI'), n=2)
    # Legacy path. Just return a single entry list with the old path.
    return [os.path.join(tree, 'usr/lib/bootupd/updates/EFI')]


def find_efi_vendor_dir_name(efidir=None, source_tree=None):
    """
    Searches either an EFI directory structure (efidir) or a source tree
    (source_tree) for an EFI vendor directory name (usually fedora,
    redhat, or centos). If source_tree is given the efidir will be found
    first using find_efi_source_paths().
    """
    if source_tree and efidir:
        raise ValueError("find_efi_vendor_dir_name: cannot pass both efidir and source_tree")
    if not source_tree and not efidir:
        raise ValueError("find_efi_vendor_dir_name: must pass either efidir or source_tree")
    # If the user provided a source_tree and not an efidir then
    # we must first find the efidir within the source_tree.
    if source_tree:
        # To find the string for the vendor ID we only need to inspect one
        # of the source EFI directories. Grab one here.
        efidir = find_efi_source_paths(source_tree)[0]
    # Find name of vendor directory for this distro. i.e. "fedora" or "redhat".
    dirs = [n for n in os.listdir(efidir) if n != "BOOT"]
    if len(dirs) != 1:
        raise ValueError(f"did not find exactly one EFI vendor ID: {dirs}")
    vendor_id = dirs[0]
    return vendor_id


def mkefidir(efidir, source_tree):
    """
    Searches the source_tree for files used for EFI booting and copies
    these files into the specified efidir.
    """
    for path in find_efi_source_paths(source_tree):
        shutil.copytree(path, efidir, dirs_exist_ok=True)

    vendor_id = find_efi_vendor_dir_name(efidir=efidir)

    # Delete fallback and its CSV file.  Its purpose is to create
    # EFI boot variables, which we don't want when booting from
    # removable media.
    #
    # A future shim release will merge fallback.efi into the main
    # shim binary and enable the fallback behavior when the CSV
    # exists.  But for now, fail if fallback.efi is missing.
    for path in ensure_glob(os.path.join(efidir, "BOOT", "fb*.efi")):
        os.unlink(path)
    for path in ensure_glob(os.path.join(efidir, vendor_id, "BOOT*.CSV")):
        os.unlink(path)

    # Drop vendor copies of shim; we already have it in BOOT*.EFI in
    # BOOT
    for path in ensure_glob(os.path.join(efidir, vendor_id, "shim*.efi")):
        os.unlink(path)

    # Consolidate remaining files into BOOT.  shim needs GRUB to be
    # there, and the rest doesn't hurt.
    for path in ensure_glob(os.path.join(efidir, vendor_id, "*")):
        shutil.move(path, os.path.join(efidir, "BOOT"))
    os.rmdir(os.path.join(efidir, vendor_id))


def mkefiboot(efidir, output_efiboot_img, loop_client):
    """
    Creates an efi boot image file at output_efiboot_img (usually named efiboot.img),
    which is required for EFI booting. This is a fat32 formatted filesystem that
    contains all the files needed for EFI boot.
    """

    # In restrictive environments, setgid, setuid and ownership changes
    # may be restricted. This sets the file ownership to root and
    # removes the setgid and setuid bits in the tarball.
    def strip_tar(tarinfo):
        tarinfo.uid = 0
        tarinfo.gid = 0
        if tarinfo.isdir():
            tarinfo.mode = 0o755
        elif tarinfo.isfile():
            tarinfo.mode = 0o0644
        return tarinfo

    # Install binaries from the efidir
    # Manually construct the tarball to ensure proper permissions and ownership
    efitarfile = tempfile.NamedTemporaryFile(suffix=".tar")
    with tarfile.open(efitarfile.name, "w:", dereference=True) as tar:
        tar.add(efidir, arcname="/EFI", filter=strip_tar)

    # Create the efiboot image file. Determine the size we should make
    # it by taking the tarball size and adding 2MiB for fs overhead.
    size = os.path.getsize(efitarfile.name) + 2 * 1024 * 1024
    with open(output_efiboot_img, "wb") as out:
        out.truncate(size)

    # Make loopback device; mkfs; populate with files
    with loop_client.device(output_efiboot_img) as loopdev:
        # On RHEL 8, when booting from a disk device (rather than a CD),
        # https://github.com/systemd/systemd/issues/14408 causes the
        # hybrid ESP to race with the ISO9660 filesystem for the
        # /dev/disk/by-label symlink unless the ESP has its own label,
        # so set EFI-SYSTEM for consistency with the metal image.
        # This should not be needed on Fedora or RHEL 9, but seems like
        # a good thing to do anyway.
        label = 'EFI-SYSTEM'
        # NOTE: the arguments to mkfs here match how virt-make-fs calls mkfs
        subprocess.check_call(['mkfs', '-t', 'vfat', '-I', '--mbr=n', '-n', label, loopdev])
        with tempfile.TemporaryDirectory() as d:
            try:
                subprocess.check_call(['mount', '-o', 'utf8', loopdev, d])
                subprocess.check_call(['tar', '-C', d, '-xf', efitarfile.name])
            finally:
                subprocess.check_call(['umount', d])
