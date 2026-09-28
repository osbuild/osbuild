import pytest

DEVICES_NAME = "org.osbuild.luks2"


@pytest.mark.parametrize("parent,options,expected_parent_path,expect_assertion", [
    ("loop2", {}, "/dev/loop2", False),
    ("loop0", {"partnum": 5}, "/dev/loop0p5", False),
    ("/dev/loop2", {}, None, True),
])
def test_luks2_get_parent_path(
    devices_module, parent, options, expected_parent_path, expect_assertion
):
    if expect_assertion:
        with pytest.raises(AssertionError):
            devices_module.get_parent_path(parent, options)
    else:
        parent_path = devices_module.get_parent_path(parent, options)
        assert parent_path == expected_parent_path
