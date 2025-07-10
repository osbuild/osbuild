#!/usr/bin/python3
from unittest import mock

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.vagrant"


# Prepare dataset containing good and bad API call parameters
@pytest.mark.parametrize("test_data, expected_err", [
    # Bad API parameters
    ({}, "not valid under any of the given schemas"),
    ({"provider": "none"}, "not valid under any of the given schemas"),
    ({"provider": "virtualbox"}, "not valid under any of the given schemas"),
    ({"provider": "virtualbox", "virtualbox": {}}, "not valid under any of the given schemas"),
    ({"provider": "libvirt", "virtualbox": {"mac_address": "1"}}, "not valid under any of the given schemas"),
    ({"provider": "libvirt", "synced_folders": {"/vagrant": {"type": "vboxfs"}}}, "not valid under any of the given schemas"),
    # Good API parameters
    ({"provider": "libvirt"}, ""),
    ({"provider": "virtualbox", "virtualbox": {"mac_address": "000000000000"},
      "synced_folders": {"/vagrant": {"type": "rsync"}}}, ""),
])
# This test validates only API calls using correct and incorrect queries
def test_schema_validation_vagrant(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
        "devices": {
            "device": {
                "path": "some-path",
            },
        },
        "options": {
        }
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False, f"err: {[e.as_dict() for e in res.errors]}"
        testutil.assert_jsonschema_error_contains(res, expected_err)


@mock.patch("subprocess.run")
def test_vagrant_writes_file_without_rsync_when_guest_additions(_mock_run, tmp_path, stage_module):
    treepath = tmp_path / "tree"
    treepath.mkdir()

    vagrantfile = treepath / "Vagrantfile"
    metadatafile = treepath / "metadata.json"

    options = {
        "provider": "virtualbox",
        "virtualbox": {
            "mac_address": "000000000000",
        },
        "synced_folders": {
            "/vagrant": {
                "type": "rsync",
            },
        }
    }

    inputs = {
        "image": {
            "path": "/foo",
            "data": {
                "files": {
                    "image.vmdk": {"path": "foo.vmdk"}
                }
            }
        }
    }

    stage_module.main(treepath, options, inputs)

    assert vagrantfile.exists()
    assert metadatafile.exists()

    assert vagrantfile.read_text() == """Vagrant.configure("2") do |config|
    config.vm.base_mac = "000000000000"
    config.vm.synced_folder ".", "/vagrant", type: "rsync"

end
"""

    assert metadatafile.read_text() == '{"provider": "virtualbox"}'


@mock.patch("subprocess.run")
@mock.patch("subprocess.check_output")
def test_vagrant_writes_file_for_libvirt(mock_check_output, _mock_run, tmp_path, stage_module):
    mock_check_output.return_value = '{"virtual-size": 1000000000}'

    treepath = tmp_path / "tree"
    treepath.mkdir()

    vagrantfile = treepath / "Vagrantfile"
    metadatafile = treepath / "metadata.json"

    options = {
        "provider": "libvirt",
    }

    inputs = {
        "image": {
            "path": "/foo",
            "data": {
                "files": {
                    "image.vmdk": {"path": "foo.vmdk"}
                }
            }
        }
    }

    stage_module.main(treepath, options, inputs)

    assert vagrantfile.exists()
    assert metadatafile.exists()

    assert vagrantfile.read_text() == """Vagrant.configure("2") do |config|
    config.vm.provider :libvirt do |libvirt|
  libvirt.driver = "kvm"
end

end
"""

    assert metadatafile.read_text() == '{"provider": "libvirt", "format": "qcow2", "virtual_size": 1}'
