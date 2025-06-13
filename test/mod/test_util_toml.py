#
# Tests for the 'osbuild.util.toml' module
#
import os
from tempfile import TemporaryDirectory

import pytest

from osbuild.util import toml

data_obj = {
    "top": {
        "t2-1": {
            "list": ["a", "b", "c"]
        },
        "t2-2": {
            "str": "test"
        }
    }
}

data_str = """
[top.t2-1]
list = ["a", "b", "c"]

[top.t2-2]
str = "test"
"""


@pytest.mark.tomlwrite
def test_write_read():
    with TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.toml")
        toml.dump_to_file(data_obj, path)
        rdata = toml.load_from_file(path)
        assert data_obj == rdata


def test_read():
    with TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test.toml")
        with open(path, "w", encoding="utf-8") as test_file:
            test_file.write(data_str)
        rdata = toml.load_from_file(path)
        assert rdata == data_obj
