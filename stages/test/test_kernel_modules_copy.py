import os

import pytest

STAGE_NAME = "org.osbuild.kernel-modules.copy"


@pytest.mark.parametrize("version", ["7.3.4-300.fc45.x86_64", "", ".", "..", "../outside"])
def test_schema(stage_schema, version):
    result = stage_schema.validate({"type": STAGE_NAME, "options": {"kernel_version": version}})
    assert result.valid == (version == "7.3.4-300.fc45.x86_64")


def test_copy_module_tree(tmp_path, stage_module):
    source = tmp_path / "source"
    tree = tmp_path / "tree"
    version = "7.3.4-300.fc45.x86_64"
    modules = source / "usr/lib/modules" / version
    (modules / "kernel/drivers").mkdir(parents=True)
    (modules / "kernel/drivers/test.ko.xz").write_bytes(b"module")
    (modules / "kernel/drivers/test.ko.xz").chmod(0o640)
    (modules / "modules.dep").write_text("kernel/drivers/test.ko.xz:\n")
    (modules / "modules.dep.bin").write_bytes(b"index")
    (modules / "extra").mkdir()
    (modules / "extra/test.ko.xz").symlink_to("../kernel/drivers/test.ko.xz")
    (modules / "build").symlink_to("/usr/src/kernels/" + version)
    (modules / "source").symlink_to("build")
    for name in ["vmlinuz", ".vmlinuz.hmac", "vmlinux", "initramfs.img", "initrd.img", "config", "System.map"]:
        (modules / name).write_text("excluded")
    other = source / "usr/lib/modules/other"
    other.mkdir()
    (other / "vmlinuz").write_text("other kernel")
    firmware = source / "usr/lib/firmware"
    firmware.mkdir()
    (firmware / "test.bin").write_bytes(b"firmware")

    stage_module.main({"tree": {"path": str(source)}}, str(tree), {"kernel_version": version})

    target = tree / "usr/lib/modules" / version
    assert sorted(p.name for p in target.iterdir()) == ["extra", "kernel", "modules.dep", "modules.dep.bin"]
    assert (target / "kernel/drivers/test.ko.xz").read_bytes() == b"module"
    assert (target / "kernel/drivers/test.ko.xz").stat().st_mode & 0o777 == 0o640
    assert (target / "modules.dep.bin").read_bytes() == b"index"
    assert os.readlink(target / "extra/test.ko.xz") == "../kernel/drivers/test.ko.xz"
    assert not (tree / "usr/lib/modules/other").exists()
    assert not (tree / "usr/lib/firmware").exists()


def test_missing_kernel(tmp_path, stage_module):
    with pytest.raises(FileNotFoundError, match="Kernel module directory not found"):
        stage_module.main({"tree": {"path": str(tmp_path)}}, str(tmp_path / "out"), {"kernel_version": "missing"})


@pytest.mark.parametrize("version", ["", ".", "..", "../outside"])
def test_invalid_version(tmp_path, stage_module, version):
    with pytest.raises(ValueError, match="Invalid kernel version"):
        stage_module.main({"tree": {"path": str(tmp_path)}}, str(tmp_path / "out"), {"kernel_version": version})
