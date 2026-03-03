import binascii
import hashlib
import lzma
import os

import pytest

SOURCES_NAME = "org.osbuild.inline"


@pytest.mark.parametrize("encoding", ["base64", "lzma+base64"])
def test_inline_fetch(tmp_path, sources_service, encoding):
    test_data = b"1234"
    hasher = hashlib.new("sha256")
    hasher.update(test_data)
    if encoding == "base64":
        encoded_data = binascii.b2a_base64(test_data)
    elif encoding == "lzma+base64":
        encoded_data = binascii.b2a_base64(lzma.compress(test_data))
    else:
        raise ValueError(f"unsupported encoding {encoding}")

    test_data_chksum = f"sha256:{hasher.hexdigest()}"
    TEST_SOURCES = {
        test_data_chksum: {
            "encoding": encoding,
            "data": encoded_data,
        },
    }
    sources_service.cache = tmp_path / "cachedir"
    sources_service.cache.mkdir()
    sources_service.tmpdir = tmp_path
    sources_service.fetch_all(TEST_SOURCES)
    assert (sources_service.cache / test_data_chksum).read_bytes() == test_data


def test_inline_copy_all(tmp_path, sources_service):
    tmpdir = tmp_path / "tmp"
    src_cache = tmp_path / "src-cache"
    dst_cache = tmp_path / "dst-cache"
    os.mkdir(tmpdir)
    os.mkdir(src_cache)
    os.mkdir(dst_cache)

    test_data = b"1234"
    hasher = hashlib.new("sha256")
    hasher.update(test_data)
    encoded_data = binascii.b2a_base64(test_data)
    test_data_chksum = f"sha256:{hasher.hexdigest()}"
    TEST_SOURCES = {
        test_data_chksum: {
            "encoding": "base64",
            "data": encoded_data,
        },
    }

    sources_service.setup({"cache": src_cache, "options": {}})
    sources_service.tmpdir = tmpdir
    sources_service.fetch_all(TEST_SOURCES)
    assert sources_service.exists(test_data_chksum, None)

    sources_service.copy_all({test_data_chksum: {}}, dst_cache)
    assert os.path.isfile(dst_cache / sources_service.content_type / test_data_chksum)
    assert (dst_cache / sources_service.content_type / test_data_chksum).read_bytes() == test_data
