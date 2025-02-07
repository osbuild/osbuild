#!/usr/bin/python3

from unittest import mock

import pytest  # type: ignore

from osbuild import testutil

STAGE_NAME = "org.osbuild.kernel-cmdline"


@pytest.mark.parametrize("options, expected", [
    ({"kernel_opts": "--custom-opt=some"}, "--custom-opt=some"),
    ({"root_fs_uuid": "some-uuid"}, "root=UUID=some-uuid"),
    ({"root_fs_uuid": "other-uuid", "kernel_opts": "--custom-opt=other"},
     "root=UUID=other-uuid --custom-opt=other"),
])
def test_kernel_cmdline(tmp_path, stage_module, options, expected):
    tree = tmp_path / "tree"
    tree.mkdir()

    stage_module.main(tree, options)
    cmdline_file = tree / "etc" / "kernel" / "cmdline"
    assert cmdline_file.exists()
    assert cmdline_file.read_text() == expected


@pytest.mark.parametrize("options, arch", [
    ({"kernel_opts": "a" * 2049}, "x86_64"),
    ({"kernel_opts": "a" * 1025}, "arm"),
    ({"kernel_opts": "a" * 2049}, "aarch64"),
    ({"kernel_opts": "a" * 257, "kernel_cmdline_size": 256}, "any"),
])
@mock.patch("platform.machine")
def test_kernel_opts_size_check(mock_machine, tmp_path, stage_module, options, arch):
    tree = tmp_path / "tree"
    tree.mkdir()
    mock_machine.return_value = arch

    with pytest.raises(ValueError) as e:
        stage_module.main(tree, options)
    assert str(e.value).startswith("The size of the kernel cmdline options cannot be larger than")


@pytest.mark.parametrize("options, expected_error", [
    ({"kernel_cmdline_size": 256}, ""),
    ({"kernel_cmdline_size": 4096}, ""),
    ({"kernel_cmdline_size": "not integer"}, "is not of type 'integer'"),
    ({"kernel_cmdline_size": 0}, "is less than the minimum of 256"),
    ({"kernel_cmdline_size": 4097}, "is greater than the maximum of 4096"),
])
def test_schema_validation_kernel_cmdline(stage_schema, options, expected_error):
    test_input = {
        "type": STAGE_NAME,
        "options": options
    }
    res = stage_schema.validate(test_input)

    if not expected_error:
        assert res.valid
    else:
        assert not res.valid
        testutil.assert_jsonschema_error_contains(res, expected_error, expected_num_errs=1)
