
import os
import subprocess
import tempfile


__all__ = [
    "TmpFs",
]


class TmpFs:
    def __init__(self, path="/run/osbuild"):
        self.path = path
        self.root = None
        self.mounted = False

    def __enter__(self):
        self.root = tempfile.mkdtemp(prefix="osbuild-tmpfs-", dir=self.path)
        try:
            subprocess.run(["mount", "-t", "tmpfs", "-o", "mode=0755", "tmpfs", self.root], check=True)
            self.mounted = True
        except subprocess.CalledProcessError:
            os.rmdir(self.root)
            self.root = None
            raise
        return self.root

    def __exit__(self, exc_type, exc_value, exc_tb):
        if not self.root:
            return
        if self.mounted:
            subprocess.run(["umount", "--lazy", self.root], check=True)
            self.mounted = False
        os.rmdir(self.root)
        self.root = None
