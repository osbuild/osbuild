import errno
import json
import os
import stat


#pylint: disable=too-many-branches
def treesum(m, dir_fd):
    """Compute a content hash of a filesystem tree

    Parameters
    ----------
    m : hash object
        the hash object to append the treesum to
    dir_fd : int
        directory file descriptor number to operate on

    The hash is stable between runs, and guarantees that two filesystem
    trees with the same hash, are functionally equivalent from the OS
    point of view.

    The file, symlink and directory names and contents are recursively
    hashed, together with security-relevant metadata."""

    with os.scandir(f"/proc/self/fd/{dir_fd}") as it:
        for dirent in sorted(it, key=(lambda d: d.name)):
            stat_result = dirent.stat(follow_symlinks=False)
            metadata = {}
            metadata["name"] = os.fsdecode(dirent.name)
            metadata["mode"] = stat_result.st_mode
            metadata["uid"] = stat_result.st_uid
            metadata["gid"] = stat_result.st_gid
            # include the size of symlink target/file-contents so we don't have to delimit it
            metadata["size"] = stat_result.st_size
            # getxattr cannot operate on a dir_fd, so do a trick and rely on the entries in /proc
            stable_file_path = os.path.join(f"/proc/self/fd/{dir_fd}", dirent.name)
            try:
                selinux_label = os.getxattr(stable_file_path, b"security.selinux", follow_symlinks=False)
            except OSError as e:
                # SELinux support is optional
                if e.errno != errno.ENODATA:
                    raise
            else:
                metadata["selinux"] = os.fsdecode(selinux_label)
            # hash the JSON representation of the metadata to stay unique/stable/well-defined
            m.update(json.dumps(metadata, sort_keys=True).encode())
            if dirent.is_symlink():
                m.update(os.fsdecode(os.readlink(dirent.name, dir_fd=dir_fd)).encode())
            else:
                fd = os.open(dirent.name, flags=os.O_RDONLY, dir_fd=dir_fd)
                try:
                    if dirent.is_dir(follow_symlinks=False):
                        treesum(m, fd)
                    elif dirent.is_file(follow_symlinks=False):
                        # hash a page at a time (using f with fd as default is a hack to please pylint)
                        for byte_block in iter(lambda f=fd: os.read(f, 4096), b""):
                            m.update(byte_block)
                    elif stat.S_ISCHR(stat_result.st_mode) or stat.S_ISBLK(stat_result.st_mode):
                        m.update(json.dumps({"dev": stat_result.st_rdev}).encode())
                    else:
                        raise ValueError("Found unexpected filetype on OS image.")
                finally:
                    os.close(fd)
