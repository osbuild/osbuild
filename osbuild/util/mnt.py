"""Mount utilities
"""

import contextlib
import subprocess

from types import TracebackType
from typing import List, Dict, Optional, Type


def mount(source: str, target: str, bind: bool = True, ro: bool = True, private: bool = True, mode: str = "0755") -> None:
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

    r = subprocess.run(["mount"] + args + [source, target],
                       stderr=subprocess.STDOUT,
                       stdout=subprocess.PIPE,
                       encoding="utf-8",
                       check=False)

    if r.returncode != 0:
        code = r.returncode
        msg = r.stdout.strip()
        raise RuntimeError(f"{msg} (code: {code})")


def umount(target: str, lazy: bool = False) -> None:
    args = []
    if lazy:
        args += ["--lazy"]
    subprocess.run(["sync", "-f", target], check=True)
    subprocess.run(["umount", "-R"] + args + [target], check=True)


class MountGuard(contextlib.AbstractContextManager):
    mounts: List[Dict[str, str]]

    def __init__(self) -> None:
        self.mounts = []

    def mount(self, source: str, target: str, bind: bool = True, ro: bool = False, mode: str = "0755") -> None:
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

    def umount(self) -> None:

        while self.mounts:
            mnt = self.mounts.pop()  # FILO: get the last mount
            target = mnt["target"]
            # The sync should in theory not be needed but in rare
            # cases `target is busy` error has been spotted.
            # Calling  `sync` does not hurt so we keep it for now.
            subprocess.run(["sync", "-f", target], check=True)
            subprocess.run(["umount", target], check=True)

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_value: Optional[BaseException], exc_tb: Optional[TracebackType]) -> None:
        self.umount()
