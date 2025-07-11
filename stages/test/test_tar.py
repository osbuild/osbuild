#!/usr/bin/python3

import os.path
import re
import subprocess
import tarfile

import pytest

from osbuild import testutil
from osbuild.testutil import has_executable, make_fake_input_tree

STAGE_NAME = "org.osbuild.tar"


@pytest.mark.parametrize("test_data,expected_err", [
    # bad
    ({}, "'filename' is a required property"),
    ({
        "filename": "out.tar",
        "root-node": "include",
        "paths": ["file1"]
    }, "{'filename': 'out.tar', 'root-node': 'include', 'paths': ['file1']} is not valid under any of the given schemas"),
    ({
        "filename": "foo",
        "transform": ["transform-cannot-be-passed-multiple-times"],
    }, " is not of type 'string'"),
    ({
        "filename": "foo",
        "compression": "EXTREME",
    }, "'EXTREME' is not one of"),
    # good
    ({"filename": "out.tar", "root-node": "include"}, ""),
    ({"filename": "out.tar", "paths": ["file1"]}, ""),
    ({"filename": "out.tar", "sparse": True}, ""),
    ({"filename": "out.tar"}, ""),
    ({"filename": "out.tar", "transform": "s/foo/bar"}, ""),
    ({"filename": "out.tar", "compression": "auto"}, ""),
    ({"filename": "out.tar", "compression": "gzip"}, ""),
])
def test_schema_validation_tar(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "options": {
        }
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


@pytest.fixture(name="fake_inputs")
def make_fake_inputs(tmp_path):
    fake_input_tree = make_fake_input_tree(tmp_path, {
        "/file1": "A file to be tarred",
        "/file2": "Another file to be tarred",
    })
    inputs = {
        "tree": {
            "path": fake_input_tree,
        }
    }
    return inputs


@pytest.mark.skipif(not has_executable("tar"), reason="no tar executable")
def test_tar_filename(tmp_path, stage_module, fake_inputs):
    options = {
        "filename": "out.tar",
    }
    stage_module.main(fake_inputs, tmp_path, options)

    tar_path = os.path.join(tmp_path, "out.tar")
    assert os.path.exists(tar_path)
    output = subprocess.check_output(["tar", "-tf", tar_path], encoding="utf-8").strip().split("\n")
    assert sorted(["./", "./file1", "./file2"]) == sorted(output)


@pytest.mark.skipif(not has_executable("tar"), reason="no tar executable")
def test_tar_root_node_omit(tmp_path, stage_module, fake_inputs):
    options = {
        "filename": "out.tar",
        "root-node": "omit",
    }
    stage_module.main(fake_inputs, tmp_path, options)

    tar_path = os.path.join(tmp_path, "out.tar")
    assert os.path.exists(tar_path)
    output = subprocess.check_output(["tar", "-tf", tar_path], encoding="utf-8").strip().split("\n")
    assert sorted(["file1", "file2"]) == sorted(output)


@pytest.mark.skipif(not has_executable("tar"), reason="no tar executable")
def test_tar_paths(tmp_path, stage_module, fake_inputs):
    options = {
        "filename": "out.tar",
        "paths": [
            "file2",
            "file1",
            "file1",
            "file2",
        ]
    }
    stage_module.main(fake_inputs, tmp_path, options)

    tar_path = os.path.join(tmp_path, "out.tar")
    assert os.path.exists(tar_path)
    output = subprocess.check_output(["tar", "-tf", tar_path], encoding="utf-8").split("\n")
    assert ["file2", "file1", "file1", "file2", ""] == output


@pytest.mark.skipif(not has_executable("tar"), reason="no tar executable")
@pytest.mark.parametrize("transform,expected_tar_output", [
    # unrelated transform
    ("s/foo/bar/", ["file1", "file2", ""]),
    # one file
    ("s/^file1$/foo99/", ["foo99", "file2", ""]),
    # one file
    ("s/file1/foo99/;s/file2/bar11/", ["foo99", "bar11", ""]),
])
def test_tar_transform(tmp_path, stage_module, fake_inputs, transform, expected_tar_output):
    options = {
        "filename": "out.tar",
        "paths": [
            "file1",
            "file2",
        ],
        "transform": transform,
    }
    stage_module.main(fake_inputs, tmp_path, options)

    tar_path = os.path.join(tmp_path, "out.tar")
    assert os.path.exists(tar_path)
    output = subprocess.check_output(["tar", "-tf", tar_path], encoding="utf-8").split("\n")
    assert output == expected_tar_output


def test_tar_transform_no_sh(tmp_path, stage_module, fake_inputs):
    options = {
        "filename": "out.tar",
        "paths": [
            "file1",
        ],
        # GNU sed allows to run shell commands with "/e"
        # ensure here we donot allow this
        "transform": "s/file1/date/e",
    }
    with pytest.raises(subprocess.CalledProcessError) as ex:
        stage_module.main(fake_inputs, tmp_path, options)
    assert "exit status 2" in str(ex.value)


@pytest.mark.parametrize('tmp_path_disk_full_size', [5 * 1024])
@pytest.mark.skipif(os.getuid() != 0, reason="needs root")
def test_tar_disk_full(stage_module, fake_inputs, tmp_path_disk_full, capfd):
    options = {
        "filename": "out.tar",
    }

    with pytest.raises(subprocess.CalledProcessError) as ex:
        stage_module.main(fake_inputs, tmp_path_disk_full, options)

    assert ex.value.returncode == 2
    assert re.search(r"Wrote only \d+ of \d+ bytes", str(capfd.readouterr().err))


@pytest.mark.skipif(not has_executable("tar"), reason="no tar executable")
@pytest.mark.parametrize("filename,compression,expected", [
    ("out.tar.gz", "auto", "gzip"),  # Auto uses the filename, which ends in .gz and should lead to gzip
    ("out.unknown", "xz", "xz"),
    ("out.unknown", "gzip", "gzip"),
    ("out.unknown", "zstd", "zstandard"),
])
def test_tar_compress(tmp_path, stage_module, fake_inputs, filename, compression, expected):
    options = {
        "filename": filename,
        "paths": [
            "file1",
            "file2",
        ],
        "compression": compression,
    }
    stage_module.main(fake_inputs, tmp_path, options)

    tar_path = os.path.join(tmp_path, filename)
    assert os.path.exists(tar_path)
    output = subprocess.check_output(["file", tar_path], encoding="utf-8")
    assert expected in output.lower()


@pytest.mark.skipif(not has_executable("tar"), reason="no tar executable")
@pytest.mark.parametrize("numeric_owner", [True, False,])
def test_tar_numeric_owner(tmp_path, stage_module, fake_inputs, numeric_owner):
    options = {
        "filename": "out.tar",
        "numeric-owner": numeric_owner,
    }
    stage_module.main(fake_inputs, tmp_path, options)

    tar_path = os.path.join(tmp_path, "out.tar")
    assert os.path.exists(tar_path)

    # read the tar archive directly instead of relying on parsing the human-readable verbose output
    with tarfile.open(tar_path, mode="r") as archive:
        for item in archive.getmembers():
            # when enabling numeric-owner, the uname and gname fields are empty
            info = item.get_info()
            assert (info["uname"] == "") == numeric_owner
            assert (info["gname"] == "") == numeric_owner
