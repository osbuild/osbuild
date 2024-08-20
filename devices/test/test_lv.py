import pytest

DEVICES_NAME = "org.osbuild.lvm2.lv"


@pytest.mark.parametrize("parent,options,expected_parent_path", [
    ("loop2", {}, "/dev/loop2"),
    ("loop1", {"vg_partnum": 2}, "/dev/loop1p2"),
])
def test_lvm2_lv_get_parent_path(devices_module, parent, options, expected_parent_path):
    pp = devices_module.get_parent_path(parent, options)
    assert pp == expected_parent_path


def test_lvm2_escaped_lv_mapper_name(devices_module):
    expected = "1d2b2150--8de2--4b68--b387--f9bc709190e8-lvroot"
    assert devices_module.escaped_lv_mapper_name("1d2b2150-8de2-4b68-b387-f9bc709190e8", "lvroot") == expected
