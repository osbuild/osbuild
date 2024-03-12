#!/usr/bin/python3

import tempfile
from contextlib import contextmanager
from unittest.mock import Mock, call, patch

import pytest

STAGE_NAME = "org.osbuild.bootc.install-to-filesystem"


@pytest.fixture(name="mocked_named_tmp")
def mocked_named_tmp_fixture():
    fake_named_tmp = Mock()
    fake_named_tmp.name = "/tmp/fake-named-tmpfile-name"
    with patch("tempfile.NamedTemporaryFile", return_value=fake_named_tmp):
        yield


@pytest.fixture(name="mocked_temp_dir")
def mocked_temp_dir_fixture(tmp_path):
    @contextmanager
    def _tmp_dir():
        yield tmp_path
    with patch("tempfile.TemporaryDirectory", side_effect=_tmp_dir):
        yield tmp_path


FAKE_INPUTS = {
    "images": {
        "path": "/input/images/path",
        "data": {
            "archives": {
                "/input/images/path": {
                    "format": "oci-archive",
                    "name": "some-img-name",
                },
            },
        },
    }
}


@pytest.mark.parametrize("options,expected_args", [
    ({}, []),
    ({"root-ssh-authorized-keys": []}, []),
    ({"root-ssh-authorized-keys": ["ssh-key"]}, ["--root-ssh-authorized-keys", "/tmp/fake-named-tmpfile-name"]),
    ({"root-ssh-authorized-keys": ["key1", "key2"]}, ["--root-ssh-authorized-keys", "/tmp/fake-named-tmpfile-name"]),
])
@patch("subprocess.run")
def test_bootc_install_to_fs(mock_run, mocked_named_tmp, mocked_temp_dir, stage_module, options, expected_args):  # pylint: disable=unused-argument
    inputs = {
        "images": {
            "path": "/input/images/path",
            "data": {
                "archives": {
                    "/input/images/path": {
                        "format": "oci-archive",
                        "name": "some-img-name",
                    },
                },
            },
        },
    }
    paths = {
        "mounts": "/path/to/mounts",
    }

    stage_module.main(options, inputs, paths)

    assert len(mock_run.call_args_list) == 1
    assert mock_run.call_args_list == [
        call(["bootc", "install", "to-filesystem",
              "--source-imgref", f"oci-archive:{mocked_temp_dir}/image",
              "--skip-fetch-check", "--generic-image",
              ] + expected_args + ["/path/to/mounts"],
             check=True)
    ]


@patch("subprocess.run")
def test_bootc_install_to_fs_write_root_ssh_keys(mock_run, stage_module):  # pylint: disable=unused-argument
    paths = {
        "mounts": "/path/to/mounts",
    }
    options = {
        "root-ssh-authorized-keys": ["key1", "key2"],
    }

    named_tmp = tempfile.NamedTemporaryFile(delete=False)
    with patch("tempfile.NamedTemporaryFile", return_value=named_tmp):
        stage_module.main(options, FAKE_INPUTS, paths)
        with open(named_tmp.name, encoding="utf8") as fp:
            assert "key1\nkey2\n" == fp.read()
