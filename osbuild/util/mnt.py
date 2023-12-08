"""Mount utilities
"""

import contextlib
import subprocess


def _run_mount(source, target, args):
    try:
        subprocess.run(["mount"] + args + [source, target],
                       stderr=subprocess.STDOUT,
                       stdout=subprocess.PIPE,
                       encoding="utf-8",
                       check=True)
    except subprocess.CalledProcessError as e:
        code = e.returncode
        msg = e.stdout.strip()
        raise RuntimeError(f"{msg} (code: {code})") from e


def mount(source, target, bind=True, ro=True, private=True, mode="0755"):
    options = []
    if ro:
        options += ["ro"]
    if mode:
        options += [mode]

    args = []
    if bind:
        args += ["--rbind"]
    if private:
        args += ["--make-rprivate"]
    if options:
        args += ["-o", ",".join(options)]
    _run_mount(source, target, args)


def umount(target, lazy=False, recursive=True):
    args = []
    if recursive:
        args += ["-R"]
    if lazy:
        args += ["--lazy"]
    # The sync should in theory not be needed but in rare
    # cases `target is busy` error has been spotted.
    # Calling  `sync` does not hurt so we keep it for now.
    subprocess.run(["sync", "-f", target], check=True)
    subprocess.run(["umount"] + args + [target], check=True)


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
        _run_mount(source, target, args)
        self.mounts += [{"source": source, "target": target}]

    def umount(self):
        while self.mounts:
            mnt = self.mounts.pop()  # FILO: get the last mount
            umount(mnt["target"], recursive=False)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.umount()
