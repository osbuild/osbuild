"""userspace /dev device manager (udev) utilities"""

import contextlib
import pathlib

# The default lock dir to use
LOCKDIR = "/run/osbuild/locks/udev"


class UdevInhibitor:
    """
    Inhibit execution of certain udev rules for block devices

    This is the osbuild side of the custom mechanism that
    allows us to inhibit certain udev rules for block devices.

    For each device a lock file is created in a well known
    directory (LOCKDIR). A custom udev rule set[1] checks
    for the said lock file and inhibits other udev rules from
    being executed.
    See the aforementioned rules file for more information.

    [1] 10-osbuild-inhibitor.rules
    """

    def __init__(self, path: pathlib.Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def inhibit(self) -> None:
        self.path.touch()

    def release(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()

    @property
    def active(self) -> bool:
        return self.path.exists()

    def __str__(self):
        return f"UdevInhibtor at '{self.path}'"

    @classmethod
    def for_dm_name(cls, name: str, lockdir=LOCKDIR):
        """Inhibit a Device Mapper device with the given name"""
        path = pathlib.Path(lockdir, f"dm-{name}")
        ib = cls(path)
        ib.inhibit()
        return ib

    @classmethod
    def for_device(cls, major: int, minor: int, lockdir=LOCKDIR):
        """Inhibit a device given its major and minor number"""
        path = pathlib.Path(lockdir, f"device-{major}:{minor}")
        ib = cls(path)
        ib.inhibit()
        return ib
