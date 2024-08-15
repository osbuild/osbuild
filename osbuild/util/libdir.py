import os.path
from typing import List


class Libdir:
    """Libdir abstracts the osbuild --libdir handling"""

    def __init__(self, libdir: str) -> None:
        self._libdir = [os.path.abspath(p)
                        for p in libdir.split(":")]

    @property
    def libdir(self) -> str:
        """Return the libdir as a ":" separated PATH like string"""
        return ":".join(self._libdir)

    @property
    def dirs(self) -> List[str]:
        """Return a list of host libdirs"""
        return self._libdir

    @property
    def buildroot_dirs(self) -> List[str]:
        """Return a list of buildroot paths for the libdir"""
        dirs = []
        buildroot_base = "/run/osbuild/lib"
        for i in range(len(self.dirs)):
            if i == 0:
                dirs.append(buildroot_base)
            else:
                dirs.append(buildroot_base + str(i))
        return dirs

    @property
    def buildroot_libdir(self) -> str:
        """Return the buildroot libdir as a ":" separated PATH like string"""
        return ":".join(self.buildroot_dirs)
