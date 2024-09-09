import os
import subprocess


class Chroot:
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

        subprocess.run(["/usr/bin/mount", "-t", "proc", "-o", "nosuid,noexec,nodev",
                        "proc", f"{self.root}/proc"],
                       check=True)

        subprocess.run(["/usr/bin/mount", "-t", "devtmpfs", "-o", "mode=0755,noexec,nosuid,strictatime",
                        "devtmpfs", f"{self.root}/dev"],
                       check=True)

        subprocess.run(["/usr/bin/mount", "-t", "sysfs", "-o", "nosuid,noexec,nodev",
                        "sysfs", f"{self.root}/sys"],
                       check=True)

        return self

    def __exit__(self, exc_type, exc_value, tracebk):
        failed_umounts = []
        for d in ["/proc", "/dev", "/sys"]:
            if subprocess.run(["/usr/bin/umount", "--lazy", self.root + d], check=False).returncode != 0:
                failed_umounts.append(d)
        if failed_umounts:
            print(f"Error unmounting paths from chroot: {failed_umounts}")

    def run(self, cmd, **kwargs):
        cmd = ["/usr/sbin/chroot", self.root] + cmd
        # pylint: disable=subprocess-run-check
        return subprocess.run(cmd, **kwargs)  # noqa: PLW1510
