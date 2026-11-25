import os
import subprocess

import pytest

from osbuild.testutil import has_executable

STAGE_NAME = "org.osbuild.cpio.out"


@pytest.mark.skipif(not has_executable("cpio"), reason="no cpio executable")
@pytest.mark.parametrize("root_node", ["include", "omit"])
def test_cpio_directory_order_and_symlinks(tmp_path, stage_module, root_node):
    tree = tmp_path / "tree"
    bindir = tree / "usr" / "bin"
    bindir.mkdir(parents=True)
    (bindir / "example").write_text("example", encoding="utf-8")
    (tree / "bin").symlink_to("usr/bin")

    archive = tmp_path / "out.cpio"
    stage_module.main({"tree": {"path": str(tree)}}, tmp_path, {"filename": archive.name, "root-node": root_node})

    entries = subprocess.check_output(["cpio", "-it", "--quiet", "-F", archive], encoding="utf-8").splitlines()
    expected = ["bin", "usr", "usr/bin", "usr/bin/example"]
    if root_node == "include":
        expected.insert(0, ".")
    assert entries == expected

    extracted = tmp_path / "extracted"
    extracted.mkdir()
    subprocess.run(["cpio", "-i", "--quiet", "-F", archive], cwd=extracted, check=True)
    assert os.readlink(extracted / "bin") == "usr/bin"
    assert (extracted / "usr/bin/example").read_text(encoding="utf-8") == "example"
