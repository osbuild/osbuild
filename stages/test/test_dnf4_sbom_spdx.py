#!/usr/bin/python3

import pytest

import osbuild.testutil as testutil

STAGE_NAME = "org.osbuild.dnf4.sbom.spdx"


@pytest.mark.parametrize("test_data,expected_err", [
    # good
    (
        {
            "options": {
                "config": {
                    "doc_path": "/image.spdx.json",
                }
            }
        },
        "",
    ),
    (
        {
            "options": {
                "config": {
                    "doc_path": "/root/doc.spdx.json",
                }
            }
        },
        "",
    ),
    (
        {
            "options": {
                "config": {
                    "doc_path": "/image.spdx.json",
                }
            },
            "inputs": {
                "root-tree": {
                    "type": "org.osbuild.tree",
                    "origin": "org.osbuild.pipeline",
                    "references": [
                        "name:root-tree"
                    ]
                }
            }
        },
        "",
    ),
    # bad
    (
        {
            "options": {
                "config": {
                    "doc_path": "/image.spdx",
                }
            }
        },
        "'/image.spdx' does not match '^\\\\/(?!\\\\.\\\\.)((?!\\\\/\\\\.\\\\.\\\\/).)+[\\\\w]{1,250}\\\\.spdx.json$'",
    ),
    (
        {
            "options": {
                "config": {
                    "doc_path": "/image.json",
                }
            }
        },
        "'/image.json' does not match '^\\\\/(?!\\\\.\\\\.)((?!\\\\/\\\\.\\\\.\\\\/).)+[\\\\w]{1,250}\\\\.spdx.json$'",
    ),
    (
        {
            "options": {
                "config": {
                    "doc_path": "image.spdx.json",
                }
            }
        },
        "'image.spdx.json' does not match '^\\\\/(?!\\\\.\\\\.)((?!\\\\/\\\\.\\\\.\\\\/).)+[\\\\w]{1,250}\\\\.spdx.json$'",
    ),
    (
        {
            "options": {
                "config": {}
            }
        },
        "'doc_path' is a required property",
    ),
    (
        {
            "options": {}
        },
        "'config' is a required property",
    ),
    (
        {
            "options": {
                "config": {
                    "doc_path": "/image.spdx.json",
                }
            },
            "inputs": {
                "root-tree": {
                    "type": "org.osbuild.file",
                    "origin": "org.osbuild.pipeline",
                    "references": [
                        "name:root-tree"
                    ]
                }
            }
        },
        "'org.osbuild.file' is not one of ['org.osbuild.tree']",
    ),
])
@pytest.mark.parametrize("stage_schema", ["2"], indirect=True)
def test_schema_validation(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": test_data["options"],
    }
    if "inputs" in test_data:
        test_input["inputs"] = test_data["inputs"]

    res = stage_schema.validate(test_input)
    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)
