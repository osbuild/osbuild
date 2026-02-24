import json
import os
import subprocess as sp
import sys
from typing import Dict, List

import pytest

from osbuild.objectstore import ObjectStore
from osbuild.testutil.imports import import_module_from_path

osbuild_store = import_module_from_path("osbuild_store", "tools/osbuild-store")


def populate_store_with_sources(path: str, items: Dict) -> None:
    with ObjectStore(path) as store:
        # just use the inline source for all items
        srcs = os.path.join(store.store, "sources", "org.osbuild.files")
        os.makedirs(srcs)
        for item in items:
            with open(os.path.join(srcs, item), "w", encoding="utf-8") as f:
                f.write(items[item])


def diff_stores(apath: str, bpath: str) -> List:
    with ObjectStore(apath) as astore, ObjectStore(bpath) as bstore:
        asrcs = os.path.join(astore.store, "sources", "org.osbuild.files")
        afiles = os.listdir(asrcs)
        bsrcs = os.path.join(bstore.store, "sources", "org.osbuild.files")
        bfiles = os.listdir(bsrcs)
        return list(set(afiles) - set(bfiles))


@pytest.mark.parametrize(
    "manifest,store_data, diff",
    (
        (
            # both sources from the store are in the manifest
            {
                "version": "2",
                "sources": {
                    "org.osbuild.inline": {
                        "items": {
                            "sha256:6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b": {
                                "encoding": "base64",
                                "data": "MQ==",
                            },
                            "sha256:d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35": {
                                "encoding": "base64",
                                "data": "Mg==",
                            },
                        },
                    },
                },
            },
            {
                "sha256:6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b": "MQ==",
                "sha256:d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35": "Mg==",
            },
            [],
        ),
        # only one source form the store is in the manifest
        (
            {
                "version": "2",
                "sources": {
                    "org.osbuild.inline": {
                        "items": {
                            "sha256:6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b": {
                                "encoding": "base64",
                                "data": "MQ==",
                            },
                        },
                    },
                },
            },
            {
                "sha256:6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b": "MQ==",
                "sha256:d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35": "Mg==",
            },
            ["sha256:d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35"],
        ),
    ),
)
def test_export_sources(tmp_path, manifest, store_data, diff):
    src_store = tmp_path / "src"
    tgt_store = tmp_path / "tgt"
    mani = tmp_path / "mani.json"

    with open(mani, "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    populate_store_with_sources(src_store, store_data)

    p = sp.run([
        "./tools/osbuild-store",
        "--libdir",
        ".",
        "export-sources",
        "--source-store",
        str(src_store),
        "--target-store",
        str(tgt_store),
        str(mani),
    ], check=False, stdout=sp.PIPE, stderr=sys.stderr)
    assert p.returncode == 0

    assert diff_stores(src_store, tgt_store) == diff
