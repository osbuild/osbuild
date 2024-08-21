import os
import subprocess


class ChrootProcDevSys:
    """
    Sets up mounts for the virtual filesystems inside a root tree, preparing it for running commands using chroot. This
    should be used whenever a stage needs to run a command against the root tree but doesn't support a --root option or
    similar.
    Cleans up mounts when done.

    This mounts /proc, /dev, and /sys.
    """

    def __init__(self, root: str):
        self.root = root

    def __enter__(self):
        for d in ["/proc", "/dev", "/sys"]:
            if not os.path.exists(self.root + d):
                print(f"Making missing chroot directory: {d}")
                os.makedirs(self.root + d)

        subprocess.check_call(["/usr/bin/mount",
                               "-t", "proc",
                               "-o", "nosuid,noexec,nodev",
                               "proc", f"{self.root}/proc"])
        subprocess.check_call(["/usr/bin/mount",
                               "-t", "devtmpfs",
                               "-o", "mode=0755,noexec,nosuid,strictatime",
                               "devtmpfs", f"{self.root}/dev"])
        subprocess.check_call(["/usr/bin/mount",
                               "-t", "sysfs",
                               "-o", "nosuid,noexec,nodev",
                               "sysfs", f"{self.root}/sys"])

        return self

    def __exit__(self, exc_type, exc_value, tracebk):
        for d in ["/proc", "/dev", "/sys"]:
            subprocess.check_call(["/usr/bin/umount", self.root + d])
