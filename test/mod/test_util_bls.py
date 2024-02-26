#
# Test for the util/bls.py
#

import textwrap

from osbuild.util import bls


def make_fake_bls_file(rootdir, kernel_opts):
    if kernel_opts:
        options = f"options {kernel_opts}"
    else:
        options = ""
    bls_path = rootdir / "loader/entries/test.conf"
    bls_path.parent.mkdir(exist_ok=True, parents=True)
    bls_path.write_text(textwrap.dedent(f"""\
    title        Fedora 19 (Rawhide)
    sort-key     fedora
    machine-id   6a9857a393724b7a981ebb5b8495b9ea
    version      3.8.0-2.fc19.x86_64
    {options}
    architecture x64
    linux        /6a9857a393724b7a981ebb5b8495b9ea/3.8.0-2.fc19.x86_64/linux
    initrd       /6a9857a393724b7a981ebb5b8495b9ea/3.8.0-2.fc19.x86_64/initrd
    """), encoding="utf8")
    return bls_path


def test_options_append_one(tmp_path):
    bls_path = make_fake_bls_file(tmp_path, "root=/dev/sda1 quiet")
    bls.options_append(tmp_path, ["splash", "console=ttyS0"])
    new_content = bls_path.read_text(encoding="utf8")
    assert "\noptions root=/dev/sda1 quiet splash console=ttyS0\n" in new_content


def test_options_append_none(tmp_path):
    bls_path = make_fake_bls_file(tmp_path, "")
    bls.options_append(tmp_path, ["splash", "console=ttyS0"])
    new_content = bls_path.read_text(encoding="utf8")
    assert "\noptions splash console=ttyS0\n" in new_content


def test_options_append_multiple(tmp_path):
    bls_path = make_fake_bls_file(tmp_path, "root=/dev/sda1")
    with bls_path.open("a") as fp:
        fp.write("options quiet")
    bls.options_append(tmp_path, ["splash", "console=ttyS0"])
    new_content = bls_path.read_text(encoding="utf8")
    options = [line for line in new_content.split("\n")
               if line.startswith("options ")]
    # note that the new options only got added once
    assert options == [
        "options root=/dev/sda1 splash console=ttyS0",
        "options quiet",
    ]
