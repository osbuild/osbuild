import contextlib
import os
import subprocess
import sys


def skipcpio(fd):
    cpio_end = b"TRAILER!!!"
    cpio_len = len(cpio_end)
    pos = 0
    while True:
        os.lseek(fd, pos, os.SEEK_SET)
        data = os.read(fd, 2 * cpio_len)
        if data == b"":
            # end of file, cpio_end not found, cat it all
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
    n = 2 * cpio_len
    while True:
        data = os.read(fd, n)
        if data == b"":
            os.lseek(fd, pos, os.SEEK_SET)
            return 0
        for i, x in enumerate(data):
            if x != 0:
                pos += i
                os.lseek(fd, pos, os.SEEK_SET)
                return pos
        pos += len(data)
    return pos


def read_header(fd, n=6):
    pos = os.lseek(fd, 0, os.SEEK_CUR)
    hdr = os.read(fd, n)
    pos = os.lseek(fd, pos, os.SEEK_SET)
    return hdr


def is_kmod(f: str):
    return f.endswith(".ko") or f.endswith(".ko.xz")


class Initrd:
    def __init__(self, path: str):
        name = os.path.basename(path)
        if name == "initrd":
            # in the unlikely event that we actually have a fully compliant BLS entry
            # a la /6a9857a393724b7a981ebb5b8495b9ea/3.8.0-2.fc19.x86_64/initrd
            name = os.path.basename(os.path.dirname(path))
        self.path = path
        self.name = name

        self.early_cpio = False
        self.compression = None
        self._cat = None

        self._cache = {}
        self.init()

    def init(self):
        with self.open() as image:
            hdr = read_header(image)
            if hdr.startswith(b"\x71\xc7") or hdr == b"070701":
                cmd = "cpio --extract --quiet --to-stdout -- 'early_cpio'"
                data = self.run(cmd, image)
                self.early_cpio = data == "1"

            if self.early_cpio:
                skipcpio(image)
                hdr = read_header(image)
            if hdr.startswith(b"\x1f\x8b"):
                cat = "zcat --"
                compression = "gzip"
            elif hdr.startswith(b"BZh"):
                cat = "bzcat --"
                compression = "bz"
            elif hdr.startswith(b"\x71\xc7") or hdr == b"070701":
                cat = "cat --"
                compression = "ascii"
            elif hdr.startswith(b"\x02\x21"):
                cat = "lz4 -d -c"
                compression = "lz4"
            elif hdr.startswith(b"\x89LZO\0"):
                cat = "lzop -d -c"
                compression = "lzop"
            elif hdr.startswith(b"\x28\xB5\x2F\xFD"):
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
            filelist = data.split("\n")
            return filelist

    def read_modules(self):
        libdirs = ["lib64/dracut", "lib/dracut", "usr/lib64/dracut", "usr/lib/dracut"]
        paths = [f"{d}/modules.txt" for d in libdirs]
        cmd = f"{self._cat} | "
        cmd += "cpio --extract --quiet --to-stdout -- "
        cmd += " ".join(paths)

        with self.open() as image:
            data = self.run(cmd, image)
        return data.split("\n")

    def get_cached(self, name, fn):
        if name not in self._cache:
            self._cache[name] = fn()
        return self._cache[name]

    @property
    def filelist(self):
        return self.get_cached("filelist", self.read_file_list)

    @property
    def modules(self):
        return self.get_cached("modules", self.read_modules)

    @property
    def kmods(self):
        files = self.filelist
        mods = sorted(os.path.basename(f) for f in files if is_kmod(f))
        return mods

    def as_dict(self):
        return {
            "early_cpio": self.early_cpio,
            "compression": self.compression,
            "kmods": self.kmods,
            "modules": self.modules,
        }

    @contextlib.contextmanager
    def open(self, skip_cpio=True):
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
    def run(cmd, image):
        argv = ["/bin/sh", "-c", cmd]
        output = subprocess.check_output(argv, encoding=None, stdin=image, stderr=subprocess.DEVNULL)
        return output.strip().decode("utf8")


def read_initrd(path):
    initrd = Initrd(path)
    return {initrd.name: initrd.as_dict()}


def main():
    import json  # pylint: disable=import-outside-toplevel

    data = read_initrd(sys.argv[1])
    json.dump(data, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
