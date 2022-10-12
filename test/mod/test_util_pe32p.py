#
# Test for the util.lvm2 module
#

import io
import os

import pytest

from osbuild.util import pe32p

EFI_STUB = "/usr/lib/systemd/boot/efi/linuxx64.efi.stub"


def have_efi_stub() -> bool:
    return os.path.exists(EFI_STUB)


@pytest.mark.skipif(not have_efi_stub(), reason="require systemd efi stub")
def test_basic():
    with open(EFI_STUB, "rb") as f:
        coff = pe32p.read_coff_header(f)
        assert coff
        opt = pe32p.read_optional_header(f, coff)
        assert opt
        sections = pe32p.read_sections(f, coff)

    assert sections, "No sections found in stub"


@pytest.mark.skipif(not have_efi_stub(), reason="require systemd efi stub")
def test_basic_no_coff():
    # check the API versions that re-reads the CoffHeader
    with open(EFI_STUB, "rb") as f:
        coff = pe32p.read_coff_header(f)
        assert coff
        f.seek(0, io.SEEK_SET)
        opt = pe32p.read_optional_header(f)
        f.seek(0, io.SEEK_SET)
        assert opt
        f.seek(0, io.SEEK_SET)
        sections = pe32p.read_sections(f)

    assert sections, "No sections found in stub"

    with open(EFI_STUB, "rb") as f:
        coff_check = pe32p.read_coff_header(f)
        assert coff_check
        assert coff == coff_check
        opt_check = pe32p.read_optional_header(f, coff)
        assert opt_check
        assert opt == opt_check
        sections_check = pe32p.read_sections(f, coff)
        assert sections_check
        assert sections == sections_check
