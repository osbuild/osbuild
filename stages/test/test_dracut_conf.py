#!/usr/bin/python3

STAGE_NAME = "org.osbuild.dracut.conf"


def test_dracut_conf_smoke(tmp_path, stage_module):
    options = {
        "filename": "qemu.conf",
        "config": {
            "add_drivers": ["virtio_blk"],
        }
    }

    tree = tmp_path / "tree"
    stage_module.main(tree, options)
    expected_dracut_conf = tree / "usr/lib/dracut/dracut.conf.d/qemu.conf"
    assert 'add_drivers+=" virtio_blk "\n' == expected_dracut_conf.read_text()
