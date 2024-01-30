#!/usr/bin/python3

import os
import unittest.mock

import pytest

from osbuild import testutil

STAGE_NAME = "org.osbuild.machine-id"


@pytest.fixture(name="machine_id_path")
def machine_id_path_fixture(tmp_path):
    machine_id_path = tmp_path / "etc/machine-id"
    machine_id_path.parent.mkdir()
    return machine_id_path


@pytest.mark.parametrize("already_has_etc_machine_id", [True, False])
def test_machine_id_first_boot_yes(tmp_path, stage_module, machine_id_path, already_has_etc_machine_id):
    if already_has_etc_machine_id:
        machine_id_path.touch()

    stage_module.main(tmp_path, {"first-boot": "yes"})
    assert machine_id_path.read_bytes() == b"uninitialized\n"


@pytest.mark.parametrize("already_has_etc_machine_id", [True, False])
def test_machine_id_first_boot_no(tmp_path, stage_module, machine_id_path, already_has_etc_machine_id):
    if already_has_etc_machine_id:
        machine_id_path.write_bytes(b"\x01\x02\x03")

    stage_module.main(tmp_path, {"first-boot": "no"})
    assert machine_id_path.stat().st_size == 0


@pytest.mark.parametrize("already_has_etc_machine_id", [True, False])
@unittest.mock.patch("builtins.print")
def test_machine_id_first_boot_preserve(
        mock_print,
        tmp_path,
        stage_module,
        machine_id_path,
        already_has_etc_machine_id):
    if already_has_etc_machine_id:
        machine_id_path.write_bytes(b"\x01\x02\x03")

    ret = stage_module.main(tmp_path, {"first-boot": "preserve"})
    if already_has_etc_machine_id:
        assert os.stat(machine_id_path).st_size == 3
    else:
        assert ret == 1
        mock_print.assert_called_with(f"{tmp_path}/etc/machine-id cannot be preserved, it does not exist")


@pytest.mark.parametrize("test_data,expected_err", [
    ({"first-boot": "invalid-option"}, "'invalid-option' is not one of "),
])
@pytest.mark.parametrize("stage_schema", ["1"], indirect=True)
def test_machine_id_schema_validation(stage_schema, test_data, expected_err):
    test_input = {
        "name": STAGE_NAME,
        "options": {},
    }
    test_input["options"].update(test_data)
    res = stage_schema.validate(test_input)

    assert res.valid is False
    testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)


def test_machine_id_first_boot_unknown(tmp_path, stage_module):
    with pytest.raises(ValueError, match=r"unexpected machine-id mode 'invalid'"):
        stage_module.main(tmp_path, {"first-boot": "invalid"})
