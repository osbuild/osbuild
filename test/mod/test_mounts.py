from unittest.mock import Mock

from osbuild.meta import ModuleInfo
from osbuild.mounts import Mount


def test_mount_calc_id_is_stable():
    info = Mock(spec=ModuleInfo)
    info.name = "some-name"
    device = Mock(spec=ModuleInfo)
    device.id = "some-id"
    partition = 1
    target = "/"
    opts = {"opt1": 1}
    # make sure to update Mount.calc_id and this test when adding
    # parameters here
    mount1 = Mount("name", info, device, partition, target, opts)
    assert mount1.id == "15066da9ff760a60f1d1a360de2ad584cc0c97d6f6034e3258b3275ba3da6bb2"
    mount2 = Mount("name", info, device, partition, target, opts)
    assert mount1.id == mount2.id
