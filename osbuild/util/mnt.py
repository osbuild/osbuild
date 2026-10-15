"""Mount utilities
"""

import contextlib
import enum
import json
import os
import subprocess
from typing import Optional


class MountPermissions(enum.Enum):
    READ_WRITE = "rw"
    READ_ONLY = "ro"


def _set_mount_permissions_recursive(target, permissions):
    # rw=recursive/ro=recursive requires util-linux >= 2.39. Individual bind
    # remounts work everywhere and preserve the child mounts.
    # This is not an atomic operation: other processes must not use the tree until
    # every remount has completed.
    target = os.path.realpath(target)

    result = subprocess.run(
        ["findmnt", "--json", "--list", "--submounts", "--mountpoint", target,
         "--output", "TARGET,VFS-OPTIONS"],
        stdout=subprocess.PIPE, encoding="utf-8", check=True,
    )

    mounts = {entry["target"]: entry["vfs-options"]
              for entry in json.loads(result.stdout)["filesystems"]}

    if target not in mounts or any(os.path.commonpath([target, path]) != target for path in mounts):
        raise RuntimeError(f"Invalid mount subtree for {target}")

    for path, current_options in mounts.items():
        # Preserve each mount's other flags, including nosuid/nodev/noexec, only swap
        # ro for rw.
        options = [opt for opt in current_options.split(",") if opt not in ("ro", "rw")]
        options += ["remount", "bind", permissions.value]
        subprocess.run(["mount", "-o", ",".join(options), "none", path], check=True)


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
    subprocess.run(["umount", "--lazy"] + args + [target], check=True)


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
            mode="0755", *,
            recursive_permissions=False):
        """Mount a tree with the requested permissions on its root mount.

        Set recursive_permissions to apply explicit permissions to the target
        and all its existing child mounts, preserving their other VFS flags.
        This requires multiple remounts; the tree must not be used concurrently.
        """
        if recursive_permissions and permissions is None:
            raise ValueError("recursive_permissions requires explicit permissions")
        self.remount = remount
        options = []
        if bind:
            options += ["rbind"]
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
        if recursive_permissions:
            _set_mount_permissions_recursive(target, permissions)

    def umount(self):

        while self.mounts:
            mnt = self.mounts.pop()  # FILO: get the last mount
            target = mnt["target"]
            # The sync should in theory not be needed but in rare
            # cases `target is busy` error has been spotted.
            # Calling  `sync` does not hurt so we keep it for now.
            if not self.remount:
                subprocess.run(["sync", "-f", target], check=True)
                subprocess.run(["umount", "--lazy", target], check=True)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.umount()
