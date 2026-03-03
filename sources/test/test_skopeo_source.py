#!/usr/bin/python3

import os

SOURCES_NAME = "org.osbuild.skopeo"


def test_skopeo_copy_all(tmp_path, sources_service):
    src_cache = tmp_path / "src-cache"
    dst_cache = tmp_path / "dst-cache"
    os.mkdir(src_cache)
    os.mkdir(dst_cache)

    sources_service.setup({"cache": src_cache, "options": {}})

    # simulate a container in the store
    checksum = "sha256:ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"
    os.makedirs((src_cache / sources_service.content_type / checksum / "image"))
    (src_cache / sources_service.content_type / checksum / "image" / "version").write_text("Directory Transport Version: 1.1")
    (src_cache / sources_service.content_type / checksum /
     "image" / "manifest.json").write_text("{\"schemaVersion\":2}")
    (src_cache / sources_service.content_type / checksum / "image" /
     "1111111111111111111111111111111111111111111111111111111111111111").write_text("1")
    (src_cache / sources_service.content_type / checksum / "image" /
     "2222222222222222222222222222222222222222222222222222222222222222").write_text("2")

    assert sources_service.exists(checksum, None)
    sources_service.copy_all({checksum: {}}, dst_cache)
    assert os.path.isdir(dst_cache / sources_service.content_type / checksum / "image")
    assert (dst_cache / sources_service.content_type / checksum / "image" /
            "version").read_text() == "Directory Transport Version: 1.1"
    assert (dst_cache / sources_service.content_type / checksum / "image" /
            "manifest.json").read_text() == "{\"schemaVersion\":2}"
    assert (dst_cache / sources_service.content_type / checksum / "image" /
            "1111111111111111111111111111111111111111111111111111111111111111").read_text() == "1"
    assert (dst_cache / sources_service.content_type / checksum / "image" /
            "2222222222222222222222222222222222222222222222222222222222222222").read_text() == "2"
