"""Mount utilities
"""
import contextlib
import ctypes
import enum
import subprocess
from typing import Optional

import osbuild.util.linux


class MountPermissions(enum.Enum):
    READ_WRITE = "rw"
    READ_ONLY = "ro"


def mount_new(source: str, target: str, bind: bool = True, ro: bool = True, private: bool = True, mode: str = "0755"):
    libc = osbuild.util.linux.Libc.default()

    options = []
    if ro:
        options += ["ro"]
    if mode:
        options += [mode]
    kopts = ",".join(options).encode("utf-8")

    flags = ctypes.c_ulong(0)
    if bind:
        flags = flags or libc.MS_BIND or libc.MS_REC
    if private:
        flags = flags or libc.MS_PRIVATE

    libc.mount(source, target, b"none", flags, kopts)


def mount(source, target, bind=True, ro=True, private=True, mode="0755"):
    options = []
    if ro:
        options += [MountPermissions.READ_ONLY.value]
    if mode:
        options += [mode]

    args = []
    if bind:
        args += ["--rbind"]
    if private:
        args += ["--make-rprivate"]
    if options:
        args += ["-o", ",".join(options)]

    r = subprocess.run(["mount"] + args + [source, target],
                       stderr=subprocess.STDOUT,
                       stdout=subprocess.PIPE,
                       encoding="utf-8",
                       check=False)

    if r.returncode != 0:
        code = r.returncode
        msg = r.stdout.strip()
        raise RuntimeError(f"{msg} (code: {code})")


def umount(target, lazy=False):
    args = []
    if lazy:
        args += ["--lazy"]
    subprocess.run(["sync", "-f", target], check=True)
    subprocess.run(["umount", "-R"] + args + [target], check=True)


class MountGuard(contextlib.AbstractContextManager):
    def __init__(self):
        self.mounts = []
        self.remount = False

    def mount(
            self,
            source,
            target,
            bind=True,
            remount=False,
            permissions: Optional[MountPermissions] = None,
            mode="0755"):
        self.remount = remount
        options = []
        if bind:
            options += ["bind"]
        if remount:
            options += ["remount"]
        if permissions:
            if permissions not in list(MountPermissions):
                raise ValueError(f"unknown filesystem permissions: {permissions}")
            options += [permissions.value]
        if mode:
            options += [mode]

        args = ["--make-private"]
        if options:
            args += ["-o", ",".join(options)]

        r = subprocess.run(["mount"] + args + [source, target],
                           stderr=subprocess.STDOUT,
                           stdout=subprocess.PIPE,
                           encoding="utf-8",
                           check=False)
        if r.returncode != 0:
            code = r.returncode
            msg = r.stdout.strip()
            raise RuntimeError(f"{msg} (code: {code})")

        self.mounts += [{"source": source, "target": target}]

    def umount(self):

        while self.mounts:
            mnt = self.mounts.pop()  # FILO: get the last mount
            target = mnt["target"]
            # The sync should in theory not be needed but in rare
            # cases `target is busy` error has been spotted.
            # Calling  `sync` does not hurt so we keep it for now.
            if not self.remount:
                subprocess.run(["sync", "-f", target], check=True)
                subprocess.run(["umount", target], check=True)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.umount()
