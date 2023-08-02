#!/usr/bin/python3
"""
Utility functions to read and write LVM metadata.

This module provides a `Disk` class that can be used
to read in LVM images and explore and manipulate its
metadata directly, i.e. it reads and writes the data
and headers directly. This allows one to rename an
volume group without having to involve the kernel,
which does not like to have two active LVM volume
groups with the same name.

The struct definitions have been taken from upstream
LVM2 sources[1], specifically:
  - `lib/format_text/layout.h`
  - `lib/format_text/format-text.c`

[1] https://github.com/lvmteam/lvm2 (commit 8801a86)
"""

import binascii
import io
import json
import os
import re
import struct
import sys
from collections import OrderedDict
from typing import BinaryIO, ClassVar, Dict, List, Union

PathLike = Union[str, bytes, os.PathLike]

INITIAL_CRC = 0xF597A6CF
MDA_HEADER_SIZE = 512


def _calc_crc(buf, crc=INITIAL_CRC):
    crc = crc ^ 0xFFFFFFFF
    crc = binascii.crc32(buf, crc)
    return crc ^ 0xFFFFFFFF


class CStruct:
    class Field:
        def __init__(self, name: str, ctype: str, position: int):
            self.name = name
            self.type = ctype
            self.pos = position

    def __init__(self, mapping: Dict, byte_order="<"):
        fmt = byte_order
        self.fields = []
        for pos, name in enumerate(mapping):
            ctype = mapping[name]
            fmt += ctype
            field = self.Field(name, ctype, pos)
            self.fields.append(field)
        self.struct = struct.Struct(fmt)

    @property
    def size(self):
        return self.struct.size

    def unpack(self, data):
        up = self.struct.unpack_from(data)
        res = {field.name: up[idx] for idx, field in enumerate(self.fields)}
        return res

    def read(self, fp):
        pos = fp.tell()
        data = fp.read(self.size)

        if len(data) < self.size:
            return None

        res = self.unpack(data)
        res["_position"] = pos
        return res

    def pack(self, data):
        values = [data[field.name] for field in self.fields]
        data = self.struct.pack(*values)
        return data

    def write(self, fp, data: Dict, *, offset=None):
        packed = self.pack(data)

        save = None
        if offset:
            save = fp.tell()
            fp.seek(offset)

        fp.write(packed)

        if save:
            fp.seek(save)

    def __getitem__(self, name):
        for f in self.fields:
            if f.name == f:
                return f
        raise KeyError(f"Unknown field '{name}'")

    def __contains__(self, name):
        return any(field.name == name for field in self.fields)


class Header:
    """Abstract base class for all headers"""

    struct: ClassVar[Union[struct.Struct, CStruct]]
    """Definition of the underlying struct data"""

    def __init__(self, data):
        self.data = data

    def __getitem__(self, name):
        assert name in self.struct
        return self.data[name]

    def __setitem__(self, name, value):
        assert name in self.struct
        self.data[name] = value

    def pack(self):
        return self.struct.pack(self.data)

    @classmethod
    def read(cls, fp):
        data = cls.struct.read(fp)  # pylint: disable=no-member
        return cls(data)

    def write(self, fp):
        raw = self.pack()
        fp.write(raw)

    def __str__(self) -> str:
        msg = f"{self.__class__.__name__}:"

        if not isinstance(self.struct, CStruct):
            raise RuntimeError("No field support on Struct")

        for f in self.struct.fields:
            msg += f"\n\t{f.name}: {self[f.name]}"
        return msg


class LabelHeader(Header):

    struct = CStruct(
        {  # 32 bytes on disk
            "id": "8s",  # int8_t[8] // LABELONE
            "sector": "Q",  # uint64_t  // Sector number of this label
            "crc": "L",  # uint32_t  // From next field to end of sector
            "offset": "L",  # uint32_t  // Offset from start of struct to contents
            "type": "8s",  # int8_t[8] // LVM2 00
        }
    )

    LABELID = b"LABELONE"

    # scan sector 0 to 3 inclusive
    LABEL_SCAN_SECTORS = 4

    def __init__(self, data):
        super().__init__(data)
        self.sector_size = 512

    @classmethod
    def search(cls, fp, *, sector_size=512):
        fp.seek(0, io.SEEK_SET)
        for _ in range(cls.LABEL_SCAN_SECTORS):
            raw = fp.read(sector_size)
            if raw[0 : len(cls.LABELID)] == cls.LABELID:
                data = cls.struct.unpack(raw)
                return LabelHeader(data)
        return None

    def read_pv_header(self, fp):
        sector = self.data["sector"]
        offset = self.data["offset"]
        offset = sector * self.sector_size + offset
        fp.seek(offset)
        return PVHeader.read(fp)


class DiskLocN(Header):

    struct = CStruct(
        {"offset": "Q", "size": "Q"}  # uint64_t // Offset in bytes to start sector  # uint64_t // Size in bytes
    )

    @property
    def offset(self):
        return self.data["offset"]

    @property
    def size(self):
        return self.data["size"]

    def read_data(self, fp: BinaryIO):
        fp.seek(self.offset)
        data = fp.read(self.size)
        return io.BytesIO(data)

    @classmethod
    def read_array(cls, fp):
        while True:
            data = cls.struct.read(fp)

            if not data or data["offset"] == 0:
                break

            yield DiskLocN(data)


class PVHeader(Header):

    ID_LEN = 32
    struct = CStruct({"uuid": "32s", "disk_size": "Q"})  # int8_t[ID_LEN]  # uint64_t // size in bytes
    # followed by two NULL terminated list of data areas
    # and metadata areas of type `DiskLocN`

    def __init__(self, data, data_areas, meta_areas):
        super().__init__(data)
        self.data_areas = data_areas
        self.meta_areas = meta_areas

    @property
    def uuid(self):
        return self.data["uuid"]

    @property
    def disk_size(self):
        return self.data["disk_size"]

    @classmethod
    def read(cls, fp):
        data = cls.struct.read(fp)

        data_areas = list(DiskLocN.read_array(fp))
        meta_areas = list(DiskLocN.read_array(fp))

        return cls(data, data_areas, meta_areas)

    def __str__(self):
        msg = super().__str__()
        if self.data_areas:
            msg += "\nData: \n\t" + "\n\t".join(map(str, self.data_areas))
        if self.meta_areas:
            msg += "\nMeta: \n\t" + "\n\t".join(map(str, self.meta_areas))
        return msg


class RawLocN(Header):
    struct = CStruct(
        {
            "offset": "Q",  # uint64_t  // Offset in bytes to start sector
            "size": "Q",  # uint64_t  // Size in bytes
            "checksum": "L",  # uint32_t  // Checksum of data
            "flags": "L",  # uint32_t  // Flags
        }
    )

    IGNORED = 0x00000001

    @classmethod
    def read_array(cls, fp: BinaryIO):
        while True:
            loc = cls.struct.read(fp)

            if not loc or loc["offset"] == 0:
                break

            yield cls(loc)


class MDAHeader(Header):
    struct = CStruct(
        {
            "checksum": "L",  # uint32_t   // Checksum of data
            "magic": "16s",  # int8_t[16] // Allows to scan for metadata
            "version": "L",  # uint32_t
            "start": "Q",  # uint64_t   // Absolute start byte of itself
            "size": "Q",  # uint64_t   // Size of metadata area
        }
    )
    # followed by a null termiated list of type `RawLocN`

    LOC_COMMITTED = 0
    LOC_PRECOMMITTED = 1

    HEADER_SIZE = MDA_HEADER_SIZE

    def __init__(self, data, raw_locns):
        super().__init__(data)
        self.raw_locns = raw_locns

    @property
    def checksum(self):
        return self.data["checksum"]

    @property
    def magic(self):
        return self.data["magic"]

    @property
    def version(self):
        return self.data["version"]

    @property
    def start(self):
        return self.data["start"]

    @property
    def size(self):
        return self.data["size"]

    @classmethod
    def read(cls, fp):
        data = cls.struct.read(fp)
        raw_locns = list(RawLocN.read_array(fp))
        return cls(data, raw_locns)

    def read_metadata(self, fp) -> "Metadata":
        loc = self.raw_locns[self.LOC_COMMITTED]
        offset = self.start + loc["offset"]
        fp.seek(offset)
        data = fp.read(loc["size"])
        md = Metadata.decode(data)
        return md

    def write_metadata(self, fp, data: "Metadata"):
        raw = data.encode()

        loc = self.raw_locns[self.LOC_COMMITTED]
        offset = self.start + loc["offset"]
        fp.seek(offset)

        n = fp.write(raw)
        loc["size"] = n
        loc["checksum"] = _calc_crc(raw)
        self.write(fp)

    def write(self, fp):
        data = self.struct.pack(self.data)

        fr = io.BytesIO()
        fr.write(data)

        for loc in self.raw_locns:
            loc.write(fr)

        l = fr.tell()
        fr.write(b"\0" * (self.HEADER_SIZE - l))

        raw = fr.getvalue()

        cs = struct.Struct("<L")
        checksum = _calc_crc(raw[cs.size :])
        self.data["checksum"] = checksum
        data = self.struct.pack(self.data)
        fr.seek(0)
        fr.write(data)

        fp.seek(self.start)
        n = fp.write(fr.getvalue())
        return n

    def __str__(self):
        msg = super().__str__()
        if self.raw_locns:
            msg += "\n\t" + "\n\t".join(map(str, self.raw_locns))
        return msg


class Metadata:
    def __init__(self, vg_name, data: OrderedDict) -> None:
        self._vg_name = vg_name
        self.data = data

    @property
    def vg_name(self) -> str:
        return self._vg_name

    @vg_name.setter
    def vg_name(self, vg_name: str) -> None:
        self.rename_vg(vg_name)

    def rename_vg(self, new_name):
        # Replace the corresponding key in the dict and
        # ensure it is always the first key
        name = self.vg_name
        d = self.data[name]
        del self.data[name]
        self.data[new_name] = d
        self.data.move_to_end(new_name, last=False)

    @classmethod
    def decode(cls, data: bytes) -> "Metadata":
        name, md = Metadata.decode_data(data.decode("utf8"))
        return cls(name, md)

    def encode(self) -> bytes:
        data = Metadata.encode_data(self.data)
        return data.encode("utf-8")

    def __str__(self) -> str:
        return json.dumps(self.data, indent=2)

    @staticmethod
    def decode_data(raw):
        substitutions = {
            r"#.*\n": "",
            r"\[": "[ ",
            r"\]": " ]",
            r'"': ' " ',
            r"[=,]": "",
            r"\s+": " ",
            r"\0$": "",
        }

        data = raw
        for pattern, repl in substitutions.items():
            data = re.sub(pattern, repl, data)

        data = data.split()

        DICT_START = "{"
        DICT_END = "}"
        ARRAY_START = "["
        ARRAY_END = "]"
        STRING_START = '"'
        STRING_END = '"'

        def next_token():
            if not data:
                return None
            return data.pop(0)

        def parse_str(val):
            result = ""

            while val != STRING_END:
                result = f"{result} {val}"
                val = next_token()

            return result.strip()

        def parse_type(val):
            # type = integer | float | string
            # integer = [0-9]*
            # float = [0-9]*'.'[0-9]*
            # string = '"'.*'"'

            if val == STRING_START:
                return parse_str(next_token())
            if "." in val:
                return float(val)
            return int(val)

        def parse_array(val):
            result = []

            while val != ARRAY_END:
                val = parse_type(val)
                result.append(val)
                val = next_token()

            return result

        def parse_section(val):
            result = OrderedDict()

            while val and val != DICT_END:
                result[val] = parse_value()
                val = next_token()

            return result

        def parse_value():
            val = next_token()

            if val == DICT_START:
                return parse_section(next_token())
            if val == ARRAY_START:
                return parse_array(next_token())

            return parse_type(val)

        name = next_token()
        obj = parse_section(name)

        return name, obj

    @staticmethod
    def encode_data(data):
        def encode_dict(d):
            s = ""
            for k, v in d.items():
                s += k
                if not isinstance(v, dict):
                    s += " = "
                else:
                    s += " "
                s += encode_val(v) + "\n"
            return s

        def encode_val(v):
            if isinstance(v, int):
                s = str(v)
            elif isinstance(v, str):
                s = f'"{v}"'
            elif isinstance(v, list):
                s = "[" + ", ".join(encode_val(x) for x in v) + "]"
            elif isinstance(v, dict):
                s = "{\n"
                s += encode_dict(v)
                s += "}\n"
            return s

        return encode_dict(data) + "\0"


class Disk:
    def __init__(self, fp, path: PathLike) -> None:
        self.fp = fp
        self.path = path

        self.lbl_hdr = None
        self.pv_hdr = None
        self.ma_headers: List[MDAHeader] = []

        try:
            self._init_headers()
        except:  # pylint: disable=broad-except
            self.fp.close()
            raise

    def _init_headers(self):
        fp = self.fp
        lbl = LabelHeader.search(fp)

        if not lbl:
            raise RuntimeError("Could not find label header")

        self.lbl_hdr = lbl
        self.pv_hdr = lbl.read_pv_header(fp)

        pv = self.pv_hdr

        for ma in pv.meta_areas:
            data = ma.read_data(self.fp)
            hdr = MDAHeader.read(data)
            self.ma_headers.append(hdr)

        if not self.ma_headers:
            raise RuntimeError("Could not find metadata header")

        md = self.ma_headers[0].read_metadata(fp)
        self.metadata = md

    @classmethod
    def open(cls, path: PathLike, *, read_only: bool = False) -> "Disk":
        mode = "rb"
        if not read_only:
            mode += "+"

        fp = open(path, mode)

        return cls(fp, path)

    def flush_metadata(self):
        for ma in self.ma_headers:
            ma.write_metadata(self.fp, self.metadata)

    def rename_vg(self, new_name):
        """Rename the volume group"""
        self.metadata.rename_vg(new_name)

    def set_description(self, desc: str) -> None:
        """Set the description of in the metadata block"""
        self.metadata.data["description"] = desc

    def set_creation_time(self, t: int) -> None:
        """Set the creation time of the volume group"""
        self.metadata.data["creation_time"] = t

    def set_creation_host(self, host: str) -> None:
        """Set the host that created the volume group"""
        self.metadata.data["creation_host"] = host

    def dump(self):
        print(self.path)
        print(self.lbl_hdr)
        print(self.pv_hdr)
        print(self.metadata)

    def __enter__(self):
        assert self.fp, "Disk not open"
        return self

    def __exit__(self, *exc_details):
        if self.fp:
            self.fp.flush()
            self.fp.close()
            self.fp = None


def main():

    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} DISK")
        sys.exit(1)

    with Disk.open(sys.argv[1]) as disk:
        disk.dump()


if __name__ == "__main__":
    main()
