import pytest

DEVICES_NAME = "org.osbuild.lvm2.lv"


@pytest.mark.parametrize("parent,options,expected_parent_path", [
    ("loop2", {}, "/dev/loop2"),
    ("loop1", {"vg_partnum": 2}, "/dev/loop1p2"),
])
def test_lvm2_lv_get_parent_path(devices_module, parent, options, expected_parent_path):
    pp = devices_module.get_parent_path(parent, options)
    assert pp == expected_parent_path
