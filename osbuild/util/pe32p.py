#!/usr/bin/python3
"""
Utility functions to inspect PE32+ (Portable Executable) files

To read all the section headers of an PE32+ file[1], while also
inspecting the individual headers, the `coff` header can be passed
to the individual function, which avoids having to re-read it:

```
with open("file.pe", "rb") as f:
    coff = pe32p.read_coff_header(f)
    opt = pe32p.read_optional_header(f, coff)
    sections = pe32p.read_sections(f, coff)
```

Passing `coff` to the functions eliminates extra i/o to seek to the correct
file positions, but it requires that the functions are called in the given
order, i.e. `read_coff_header`, `read_optional_haeder` then `read_sections`.

[1] https://learn.microsoft.com/en-us/windows/win32/debug/pe-format
"""

import enum
import io
import os
import struct
import sys
from collections import namedtuple
from typing import BinaryIO, Iterator, List, Optional, Union

PathLike = Union[str, bytes, os.PathLike]

CoffFormat = "4sHHIIIHH"
CoffHeader = namedtuple(
    "CoffHeader",
    [
        "Signature",
        "Machine",
        "NumberOfSections",
        "TimeDateStamp",
        "PointerToSymbolTable",
        "NumberOfSymbols",
        "SizeOfOptionalHeader",
        "Characteristics",
    ]
)


SectionFormat = "8sIIIIIIHHI"
SectionHeader = namedtuple(
    "SectionHeader",
    [
        "Name",
        "VirtualSize",
        "VirtualAddress",
        "SizeOfRawData",
        "PointerToRawData",
        "PointerToRelocations",
        "PointerToLinenumbers",
        "NumberOfRelocations",
        "NumberOfLinenumbers",
        "Characteristics",
    ]
)


class SectionFlags(enum.Flag):
    ALIGN_1BYTES = 0x00100000
    ALIGN_2BYTES = 0x00200000
    ALIGN_4BYTES = 0x00300000
    ALIGN_8BYTES = 0x00400000
    ALIGN_16BYTES = 0x00500000
    ALIGN_32BYTES = 0x00600000
    ALIGN_64BYTES = 0x00700000
    ALIGN_128BYTES = 0x00800000
    ALIGN_256BYTES = 0x00900000
    ALIGN_512BYTES = 0x00A00000
    ALIGN_1024BYTES = 0x00B00000
    ALIGN_2048BYTES = 0x00C00000
    ALIGN_4096BYTES = 0x00D00000
    ALIGN_8192BYTES = 0x00E00000
    ALIGN_MASK = 0x00F00000
    ALIGN_DEFAULT = ALIGN_16BYTES


OptionalFormat = "HBBIIIIIQIIHHHHHHIIIIHHQQQQII"
OptionalHeader = namedtuple(
    "OptionalHeader",
    [
        # Standard fields
        "Magic",
        "MajorLinkerVersion",
        "MinorLinkerVersion",
        "SizeOfCode",
        "SizeOfInitializedData",
        "SizeOfUninitializedData",
        "AddressOfEntryPoint",
        "BaseOfCode",
        # Windows-Specific fields (PE32+)
        "ImageBase",
        "SectionAlignment",
        "FileAlignment",
        "MajorOperatingSystemVersion",
        "MinorOperatingSystemVersion",
        "MajorImageVersion",
        "MinorImageVersion",
        "MajorSubsystemVersion",
        "MinorSubsystemVersion",
        "Reserved1",
        "SizeOfImage",
        "SizeOfHeaders",
        "CheckSum",
        "Subsystem",
        "DllCharacteristics",
        "SizeOfStackReserve",
        "SizeOfStackCommit",
        "SizeOfHeapReserve",
        "SizeOfHeapCommit",
        "LoaderFlags",
        "NumberOfRvaAndSizes",
    ]
)


def read_coff_header(f: BinaryIO) -> CoffHeader:
    """Read the Common Object File Format (COFF) Header of the open file at `f`"""

    # Quote from the "PE Format" article (see [1] in this module's doc string):
    # "[...] at the file offset specified at offset 0x3c, is a 4-byte signature
    # that identifies the file as a PE format image file. This signature is
    # 'PE\0\0' (the letters "P" and "E" followed by two null bytes). [...]
    # immediately after the signature of an image file, is a standard COFF
    # file header in the following format."
    # Our `CoffHeader` embeds the signature inside the CoffHeader.

    f.seek(0x3c, io.SEEK_SET)
    buf = f.read(struct.calcsize("I"))
    (s, ) = struct.unpack_from("I", buf)
    f.seek(int(s), io.SEEK_SET)

    buf = f.read(struct.calcsize(CoffFormat))
    coff = CoffHeader._make(struct.unpack_from(CoffFormat, buf))
    assert coff.Signature == b"PE\0\0", "Not a PE32+ file (missing PE header)"
    return coff


def read_optional_header(f: BinaryIO, coff: Optional[CoffHeader] = None) -> OptionalHeader:
    """Read the optional header of the open file at `f`

    If `coff` is passed in, the file position must point to directly after the
    COFF header, i.e. as if `read_coff_header` was just called.
    """
    if coff is None:
        coff = read_coff_header(f)

    buf = f.read(coff.SizeOfOptionalHeader)
    sz = struct.calcsize(OptionalFormat)
    assert len(buf) >= sz, "Optional header too small"
    opt = OptionalHeader._make(struct.unpack_from(OptionalFormat, buf))
    assert opt.Magic == 0x20B, f"Not a PE32+ file (magic: {opt.Magic:X})"
    return opt


def iter_sections(f: BinaryIO, coff: Optional[CoffHeader] = None) -> Iterator[SectionHeader]:
    """Iterate over all the sections in the open file at `f`

    If `coeff` is passed in, the file position must point directly after the Optional
    Header, i.e. as if `read_optional_haeder` was just called."""
    if coff is None:
        coff = read_coff_header(f)
        f.seek(coff.SizeOfOptionalHeader, io.SEEK_CUR)

    for _ in range(coff.NumberOfSections):
        buf = f.read(struct.calcsize(SectionFormat))
        yield SectionHeader._make(struct.unpack_from(SectionFormat, buf))


def read_sections(f: BinaryIO, coff: Optional[CoffHeader] = None) -> List[SectionHeader]:
    """Read all sections of the open file at `f`

    Like `iter_sections` but returns a list of `SectionHeader` objects."""
    return list(iter_sections(f, coff))


def main():

    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} FILE")
        sys.exit(1)

    with open(sys.argv[1], "rb") as f:
        coff = read_coff_header(f)
        opt = read_optional_header(f, coff)
        sections = read_sections(f, coff)

    print(coff)
    print(opt)
    for s in sections:
        print(s)

    last = sections[-1]
    print(f"{last.VirtualAddress: X}, {last.VirtualSize:X}")


if __name__ == "__main__":
    main()
