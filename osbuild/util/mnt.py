"""Mount utilities
"""

import contextlib
import subprocess


class MountGuard(contextlib.AbstractContextManager):
    def __init__(self):
        self.mounts = []

    def mount(self, source, target, bind=True, ro=False, mode="0755"):
        options = []
        if bind:
            options += ["bind"]
        if ro:
            options += ["ro"]
        if mode:
            options += [mode]

        args = ["--make-private"]
        if options:
            args += ["-o", ",".join(options)]

        subprocess.run(["mount"] + args + [source, target], check=True)
        self.mounts += [{"source": source, "target": target}]

    def umount(self):

        while self.mounts:
            mnt = self.mounts.pop()  # FILO: get the last mount
            target = mnt["target"]
            # The sync should in theory not be needed but in rare
            # cases `target is busy` error has been spotted.
            # Calling  `sync` does not hurt so we keep it for now.
            subprocess.run(["sync", "-f", target], check=True)
            subprocess.run(["umount", target], check=True)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.umount()
