#!/usr/bin/python3

import pytest

DEVICES_NAME = "org.osbuild.lvm2.lv"

mocked_lvs_output = """
{
    "report": [
        {
            "lv": [
                {"lv_name":"rootlv", "vg_name":"1d2b2150-8de2-4b68-b387-f9bc709190e8", "lv_attr":"-wi-------", "lv_size":"3.86g", "pool_lv":"", "origin":"", "data_percent":"", "metadata_percent":"", "move_pv":"", "mirror_log":"", "copy_percent":"", "convert_lv":""}
            ]
        }
    ]
}
"""

mocked_pvs_output = """
{
       "report": [
           {
               "pv": [
                   {"pv_name":"/dev/loop1p4", "vg_name":"1d2b2150-8de2-4b68-b387-f9bc709190e8", "pv_fmt":"lvm2", "pv_attr":"a--", "pv_size":"8.50g", "pv_free":"4.64g"}
               ]
           }
       ]
   }

"""


def mocked_check_output(args):
    if args[0] == "lvs":
        return mocked_lvs_output
    if args[0] == "pvs":
        return mocked_pvs_output
    pytest.fail(f"unexpected arg {args}")
    return ""


def test_lvm2_lv_auto_detect_volume_group_happy(monkeypatch, devices_service):
    monkeypatch.setattr("subprocess.check_output", mocked_check_output)
    vg_name = devices_service.auto_detect_volume_group("/dev/loop1", "rootlv")
    assert vg_name == "1d2b2150-8de2-4b68-b387-f9bc709190e8"


def test_lvm2_lv_auto_detect_volume_group_lv_not_found(monkeypatch, devices_service):
    monkeypatch.setattr("subprocess.check_output", mocked_check_output)
    with pytest.raises(RuntimeError) as exc:
        devices_service.auto_detect_volume_group("/dev/loop1", "other-lv")
    assert str(exc.value) == "cannot find other-lv on /dev/loop1"


def test_lvm2_lv_auto_detect_volume_group_wrong_device(monkeypatch, capfd, devices_service):
    monkeypatch.setattr("subprocess.check_output", mocked_check_output)
    with pytest.raises(RuntimeError) as exc:
        devices_service.auto_detect_volume_group("/dev/other/loop", "rootlv")
    assert str(exc.value) == "cannot find rootlv on /dev/other/loop"
    assert capfd.readouterr().err == "WARNING: ignoring /dev/loop1p4 because it is not on /dev/other/loop\n"
