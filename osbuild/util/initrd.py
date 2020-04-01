"""Initial RAM disk utilities

This module contains the `Initrd` class and associated helpers that
can be used to inspect the contents of an  initramfs/initrd image.

This file can be directly invoked and will then return all available
information about the given initrd as JSON. Example usage:
  `python3 osbuild/util/initrd.py initrd.img`
"""

import contextlib
import os
import subprocess
import sys
from typing import List, Dict, Union


def skipcpio(fd: int):
    """Move the offset of `fd` past the current archive"""
    cpio_end = b"TRAILER!!!"
    cpio_len = len(cpio_end)
    pos = 0
    while True:
        os.lseek(fd, pos, os.SEEK_SET)
        data = os.read(fd, 2*cpio_len)
        if data == b'':
            # end of file, cpio_end not found, rewind
            pos = 0
            break
        r = data.find(cpio_end)
        if r != -1:
            pos += r + cpio_len
            break  # found the end!
        pos += cpio_len
    os.lseek(fd, pos, os.SEEK_SET)
    if pos == 0:
        return pos
    # skip zeros
    n = 2*cpio_len
    while True:
        data = os.read(fd, n)
        if data == b'':
            os.lseek(fd, pos, os.SEEK_SET)
            return 0
        for i, x in enumerate(data):
            if x != 0:
                pos += i
                os.lseek(fd, pos, os.SEEK_SET)
                return pos
        pos += len(data)
    return pos


def read_header(fd: int, n: int = 6):
    pos = os.lseek(fd, 0, os.SEEK_CUR)
    hdr = os.read(fd, n)
    pos = os.lseek(fd, pos, os.SEEK_SET)
    return hdr


def is_kmod(f: str):
    return f.endswith(".ko") or f.endswith(".ko.xz")


class Initrd:
    """"Class to examine the contents of an initrd / initramfs

    Given a `path` to an initrd image, this class can be used
    to inspect its properties and content. The functions will
    always re-read the information from disk, but access via
    the properties is cached, so the latter is recommended.
    """
    def __init__(self, path: Union[str, bytes, os.PathLike]):
        self.path = os.path.abspath(path)
        name = os.path.basename(self.path)
        if name == "initrd":
            # in the unlikely event that we actually have a fully compliant BLS entry
            # a la /6a9857a393724b7a981ebb5b8495b9ea/3.8.0-2.fc19.x86_64/initrd
            name = os.path.basename(os.path.dirname(path))
        self.name = name

        self.early_cpio = False
        self.compression = None
        self._cat = None

        self._cache = {}
        self._init()

    def _init(self):
        with self.open() as image:
            hdr = read_header(image)
            if hdr.startswith(b'\x71\xc7') or hdr == b'070701':
                cmd = f"cpio --extract --quiet --to-stdout -- 'early_cpio'"
                data = self.run(cmd, image)
                self.early_cpio = data == '1'

            if self.early_cpio:
                skipcpio(image)
                hdr = read_header(image)
            if hdr.startswith(b'\x1f\x8b'):
                cat = "zcat --"
                compression = "gzip"
            elif hdr.startswith(b'BZh'):
                cat = "bzcat --"
                compression = "bz"
            elif hdr.startswith(b'\x71\xc7') or hdr == b'070701':
                cat = "cat --"
                compression = "ascii"
            elif hdr.startswith(b'\x02\x21'):
                cat = "lz4 -d -c"
                compression = "lz4"
            elif hdr.startswith(b'\x89LZO\0'):
                cat = "lzop -d -c"
                compression = "lzop"
            elif hdr.startswith(b'\x28\xB5\x2F\xFD'):
                cat = "zstd -d -c"
                compression = "zstd"
            else:
                cat = "xzcat --single-stream --"
                compression = "xz"

        self._cat = cat
        self.compression = compression

    def read_file_list(self):
        cmd = f"{self._cat} | cpio -it --no-absolute-filename"
        with self.open() as image:
            data = self.run(cmd, image)
            filelist = data.split('\n')
            return filelist

    def read_modules(self):
        libdirs = ["lib64/dracut", "lib/dracut",
                   "usr/lib64/dracut", "usr/lib/dracut"]
        paths = [f"{d}/modules.txt" for d in libdirs]
        cmd = f"{self._cat} | "
        cmd += "cpio --extract --quiet --to-stdout -- "
        cmd += " ".join(paths)

        with self.open() as image:
            data = self.run(cmd, image)
        return data.split("\n")

    def _get_cached(self, name, fn):
        if name not in self._cache:
            self._cache[name] = fn()
        return self._cache[name]

    @property
    def filelist(self) -> List[str]:
        """The list of all the files in the initrd"""
        return self._get_cached("filelist", self.read_file_list)

    @property
    def modules(self) -> List[str]:
        """The list of dracut modules in the initrd"""
        return self._get_cached("modules", self.read_modules)

    @property
    def kmods(self) -> List[str]:
        """The list of kernel modules in the initrd"""
        files = self.filelist
        mods = sorted(os.path.basename(f) for f in files if is_kmod(f))
        return mods

    def as_dict(self) -> Dict:
        """Return all available information as dictionary"""
        return {
            "early_cpio": self.early_cpio,
            "compression": self.compression,
            "kmods": self.kmods,
            "modules": self.modules
        }

    @contextlib.contextmanager
    def open(self, skip_cpio=True) -> int:
        """Open the image and return a file descriptor`"""
        fd = -1
        try:
            fd = os.open(self.path, os.O_RDONLY)
            if self.early_cpio and skip_cpio:
                skipcpio(fd)
            yield fd
        finally:
            if fd != -1:
                os.close(fd)

    @staticmethod
    def run(cmd, image) -> str:
        argv = ["/bin/sh", "-c", cmd]
        output = subprocess.check_output(argv,
                                         encoding=None,
                                         stdin=image,
                                         stderr=subprocess.DEVNULL)
        return output.strip().decode('utf-8')


def read_initrd(path: Union[str, bytes, os.PathLike]) -> Dict:
    """Read the initrd at `path` and return information as JSON"""
    initrd = Initrd(path)
    return {
        initrd.name: initrd.as_dict()
    }


def main():
    import json  # pylint: disable=import-outside-toplevel

    data = read_initrd(sys.argv[1])
    json.dump(data, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
