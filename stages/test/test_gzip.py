#!/usr/bin/python3

from unittest.mock import patch

import pytest

STAGE_NAME = "org.osbuild.gzip"


@pytest.mark.parametrize("test_options,expected_level", [
    # our default
    ({}, "-1"),
    # custom settings
    ({"level": "1"}, "-1"),
    ({"level": "6"}, "-6"),
    ({"level": "9"}, "-9"),
])
@patch("subprocess.run")
def test_gzip_compression_default_to_level1(mocked_run, tmp_path, stage_module, test_options, expected_level):
    inp = {
        "file": {
            "path": "/input/file/path",
            "data": {
                "files": {
                    "hash:value": "some-file",
                }
            },
        },
    }
    output = tmp_path
    options = {
        "filename": "out.tar.gz",
    }
    options.update(test_options)

    stage_module.main(inp, output, options)
    assert len(mocked_run.call_args_list) == 1
    args, kwargs = mocked_run.call_args_list[0]
    assert args == (["gzip", "--no-name", "--stdout", expected_level, "/input/file/path/hash:value"],)
    assert kwargs["check"]
    assert kwargs["stdout"].name.endswith("out.tar.gz")
