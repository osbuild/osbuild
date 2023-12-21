from unittest.mock import Mock

import pytest

from osbuild.devices import Device
from osbuild.meta import ModuleInfo
from osbuild.mounts import Mount


def test_mount_immutable_mixin():
    info = Mock(spec=ModuleInfo)
    info.name = "some-name"
    device = Mock(spec=ModuleInfo)
    device.id = "some-id"
    partition = 1
    target = "/"
    opts = {"opt1": 1}
    mnt = Mount("name", info, device, partition, target, opts)
    with pytest.raises(ValueError) as e:
        mnt.name = "new-name"
    assert str(e.value) == "cannot set 'name': Mount cannot be changed after creation"


def test_device_immutable_mixins():
    info = Mock(spec=ModuleInfo)
    info.name = "some-name"
    parent = None
    opts = {"opt1": 1}
    dev = Device("name", info, parent, opts)
    with pytest.raises(ValueError) as e:
        dev.name = "new-name"
    assert str(e.value) == "cannot set 'name': Device cannot be changed after creation"
