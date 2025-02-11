#!/usr/bin/python3

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.ovf"


# Prepare dataset containing good and bad API call parameters
@pytest.mark.parametrize("test_data, expected_err", [
    # Bad API parameters
    ({}, "'vmdk' is a required property"),
    ({"vmdk": 123}, "123 is not of type 'string'"),
    ({"vmdk": "imagename"}, "'imagename' does not match '[a-zA-Z0-9+_.-]+.vmdk'"),
    # Good API parameters
    ({"vmdk": "imagename.vmdk"}, ""),
])
# This test validates only API calls using correct and incorrect queries
def test_schema_validation_ovf(stage_schema, test_data, expected_err):
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
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


@pytest.mark.skipif(not testutil.has_executable("qemu-img"), reason="need qemu-img")
def test_ovf_default_template(tmp_path, stage_module):
    faked_vmdk_path = tmp_path / "some-image.vmdk"
    faked_vmdk_path.write_bytes(b"1234")

    opts = {
        "vmdk": faked_vmdk_path,
    }
    stage_module.main(opts, tmp_path)

    expected_template_path = tmp_path / "some-image.ovf"
    assert "other26xLinux64Guest" in expected_template_path.read_text()
