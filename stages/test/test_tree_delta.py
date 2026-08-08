#!/usr/bin/python3

import os
import stat

import pytest

from osbuild import testutil
from osbuild.testutil import make_fake_tree

STAGE_NAME = "org.osbuild.tree-delta"


def make_tree(tmp_path, name, content):
    tree = tmp_path / name
    make_fake_tree(tree, content)
    return os.fspath(tree)


def make_args(tmp_path, reference, overlay, options=None):
    output = tmp_path / "output"
    output.mkdir(exist_ok=True)
    args = {
        "tree": os.fspath(output),
        "inputs": {
            "reference": {"path": reference},
            "overlay": {"path": overlay},
        },
    }
    if options:
        args["options"] = options
    return args


def test_new_file_copied(tmp_path, stage_module):
    ref = make_tree(tmp_path, "reference", {})
    overlay = make_tree(tmp_path, "overlay", {
        "/usr/bin/hello": "hello world",
    })
    args = make_args(tmp_path, ref, overlay)

    stage_module.main(args)

    output = tmp_path / "output"
    assert (output / "usr/bin/hello").read_text() == "hello world"


def test_identical_file_excluded(tmp_path, stage_module):
    ref = make_tree(tmp_path, "reference", {
        "/usr/lib/libc.so": "base content",
    })
    overlay = make_tree(tmp_path, "overlay", {
        "/usr/lib/libc.so": "base content",
    })
    args = make_args(tmp_path, ref, overlay)

    stage_module.main(args)

    output = tmp_path / "output"
    assert not (output / "usr/lib/libc.so").exists()


def test_modified_file_copied(tmp_path, stage_module):
    ref = make_tree(tmp_path, "reference", {
        "/etc/config": "old",
    })
    overlay = make_tree(tmp_path, "overlay", {
        "/etc/config": "new",
    })
    args = make_args(tmp_path, ref, overlay)

    stage_module.main(args)

    output = tmp_path / "output"
    assert (output / "etc/config").read_text() == "new"


def test_symlink_new(tmp_path, stage_module):
    ref = make_tree(tmp_path, "reference", {})
    overlay_dir = tmp_path / "overlay"
    overlay_dir.mkdir()
    (overlay_dir / "usr" / "lib").mkdir(parents=True)
    (overlay_dir / "usr" / "lib" / "libfoo.so.1").write_text("lib")
    os.symlink("libfoo.so.1", overlay_dir / "usr" / "lib" / "libfoo.so")
    overlay = os.fspath(overlay_dir)

    args = make_args(tmp_path, ref, overlay)
    stage_module.main(args)

    output = tmp_path / "output"
    assert (output / "usr/lib/libfoo.so").is_symlink()
    assert os.readlink(output / "usr/lib/libfoo.so") == "libfoo.so.1"


def test_symlink_same_excluded(tmp_path, stage_module):
    for name in ("reference", "overlay"):
        d = tmp_path / name
        d.mkdir()
        (d / "usr" / "lib").mkdir(parents=True)
        (d / "usr" / "lib" / "libfoo.so.1").write_text("lib")
        os.symlink("libfoo.so.1", d / "usr" / "lib" / "libfoo.so")

    args = make_args(
        tmp_path,
        os.fspath(tmp_path / "reference"),
        os.fspath(tmp_path / "overlay"),
    )
    stage_module.main(args)

    output = tmp_path / "output"
    assert not (output / "usr/lib/libfoo.so").exists()


def test_symlink_different_copied(tmp_path, stage_module):
    for name, target in (("reference", "libfoo.so.1"), ("overlay", "libfoo.so.2")):
        d = tmp_path / name
        d.mkdir()
        (d / "usr" / "lib").mkdir(parents=True)
        os.symlink(target, d / "usr" / "lib" / "libfoo.so")

    args = make_args(
        tmp_path,
        os.fspath(tmp_path / "reference"),
        os.fspath(tmp_path / "overlay"),
    )
    stage_module.main(args)

    output = tmp_path / "output"
    assert (output / "usr/lib/libfoo.so").is_symlink()
    assert os.readlink(output / "usr/lib/libfoo.so") == "libfoo.so.2"


def test_new_directory_copied_wholesale(tmp_path, stage_module):
    ref = make_tree(tmp_path, "reference", {})
    overlay = make_tree(tmp_path, "overlay", {
        "/opt/app/bin/run": "#!/bin/sh\necho hi",
        "/opt/app/lib/data": "data",
    })
    args = make_args(tmp_path, ref, overlay)

    stage_module.main(args)

    output = tmp_path / "output"
    assert (output / "opt/app/bin/run").read_text() == "#!/bin/sh\necho hi"
    assert (output / "opt/app/lib/data").read_text() == "data"


def test_paths_filter(tmp_path, stage_module):
    ref = make_tree(tmp_path, "reference", {})
    overlay = make_tree(tmp_path, "overlay", {
        "/usr/bin/hello": "hello",
        "/opt/app/run": "run",
        "/etc/config": "config",
        "/var/log/messages": "log",
    })
    args = make_args(tmp_path, ref, overlay, options={"paths": ["/usr", "/opt"]})

    stage_module.main(args)

    output = tmp_path / "output"
    assert (output / "usr/bin/hello").exists()
    assert (output / "opt/app/run").exists()
    assert not (output / "etc").exists()
    assert not (output / "var").exists()


def test_exclude_paths(tmp_path, stage_module):
    ref = make_tree(tmp_path, "reference", {})
    overlay = make_tree(tmp_path, "overlay", {
        "/usr/bin/hello": "hello",
        "/usr/share/doc/readme": "docs",
        "/usr/share/doc/sub/notes": "notes",
        "/usr/share/man/man1/hello.1": "man page",
        "/opt/app/run": "run",
    })
    args = make_args(tmp_path, ref, overlay, options={
        "exclude_paths": ["/usr/share/doc"],
    })

    stage_module.main(args)

    output = tmp_path / "output"
    assert (output / "usr/bin/hello").exists()
    assert (output / "usr/share/man/man1/hello.1").exists()
    assert (output / "opt/app/run").exists()
    assert not (output / "usr/share/doc").exists()


def test_exclude_paths_with_paths_filter(tmp_path, stage_module):
    ref = make_tree(tmp_path, "reference", {})
    overlay = make_tree(tmp_path, "overlay", {
        "/usr/bin/hello": "hello",
        "/usr/share/doc/readme": "docs",
        "/opt/app/run": "run",
        "/etc/config": "config",
    })
    args = make_args(tmp_path, ref, overlay, options={
        "paths": ["/usr", "/opt"],
        "exclude_paths": ["/usr/share/doc"],
    })

    stage_module.main(args)

    output = tmp_path / "output"
    assert (output / "usr/bin/hello").exists()
    assert (output / "opt/app/run").exists()
    assert not (output / "usr/share/doc").exists()
    assert not (output / "etc").exists()


def test_exclude_paths_exact_file(tmp_path, stage_module):
    ref = make_tree(tmp_path, "reference", {})
    overlay = make_tree(tmp_path, "overlay", {
        "/usr/lib/libfoo.so": "lib",
        "/usr/lib/libbar.so": "lib",
    })
    args = make_args(tmp_path, ref, overlay, options={
        "exclude_paths": ["/usr/lib/libfoo.so"],
    })

    stage_module.main(args)

    output = tmp_path / "output"
    assert (output / "usr/lib/libbar.so").exists()
    assert not (output / "usr/lib/libfoo.so").exists()


def test_empty_overlay(tmp_path, stage_module):
    ref = make_tree(tmp_path, "reference", {
        "/usr/lib/libc.so": "content",
    })
    overlay = make_tree(tmp_path, "overlay", {})
    args = make_args(tmp_path, ref, overlay)

    stage_module.main(args)

    output = tmp_path / "output"
    assert len(list(output.iterdir())) == 0


def test_mode_difference_copied(tmp_path, stage_module):
    ref_dir = tmp_path / "reference"
    overlay_dir = tmp_path / "overlay"
    for d in (ref_dir, overlay_dir):
        d.mkdir()
        (d / "usr" / "bin").mkdir(parents=True)
        (d / "usr" / "bin" / "tool").write_text("same content")

    os.chmod(ref_dir / "usr/bin/tool", 0o644)
    os.chmod(overlay_dir / "usr/bin/tool", 0o755)

    args = make_args(tmp_path, os.fspath(ref_dir), os.fspath(overlay_dir))
    stage_module.main(args)

    output = tmp_path / "output"
    assert (output / "usr/bin/tool").exists()
    result_mode = stat.S_IMODE(os.lstat(output / "usr/bin/tool").st_mode)
    assert result_mode == 0o755


def test_hardlink_new(tmp_path, stage_module):
    ref = make_tree(tmp_path, "reference", {})
    overlay_dir = tmp_path / "overlay"
    overlay_dir.mkdir()
    (overlay_dir / "usr" / "lib").mkdir(parents=True)
    (overlay_dir / "usr" / "lib" / "libfoo.so.1").write_text("lib content")
    os.link(overlay_dir / "usr" / "lib" / "libfoo.so.1",
            overlay_dir / "usr" / "lib" / "libfoo.so.1.0")

    args = make_args(tmp_path, ref, os.fspath(overlay_dir))
    stage_module.main(args)

    output = tmp_path / "output"
    assert (output / "usr/lib/libfoo.so.1").read_text() == "lib content"
    assert (output / "usr/lib/libfoo.so.1.0").read_text() == "lib content"


def test_hardlink_same_excluded(tmp_path, stage_module):
    for name in ("reference", "overlay"):
        d = tmp_path / name
        d.mkdir()
        (d / "usr" / "lib").mkdir(parents=True)
        (d / "usr" / "lib" / "libfoo.so.1").write_text("lib content")
        os.link(d / "usr" / "lib" / "libfoo.so.1",
                d / "usr" / "lib" / "libfoo.so.1.0")

    args = make_args(
        tmp_path,
        os.fspath(tmp_path / "reference"),
        os.fspath(tmp_path / "overlay"),
    )
    stage_module.main(args)

    output = tmp_path / "output"
    assert not (output / "usr/lib/libfoo.so.1").exists()
    assert not (output / "usr/lib/libfoo.so.1.0").exists()


def test_hardlink_different_copied(tmp_path, stage_module):
    for name in ("reference", "overlay"):
        d = tmp_path / name
        d.mkdir()
        (d / "usr" / "lib").mkdir(parents=True)
        (d / "usr" / "lib" / "libfoo.so.1").write_text(f"{name} content")

    args = make_args(
        tmp_path,
        os.fspath(tmp_path / "reference"),
        os.fspath(tmp_path / "overlay"),
    )
    stage_module.main(args)

    output = tmp_path / "output"
    assert (output / "usr/lib/libfoo.so.1").read_text() == "overlay content"


def test_dir_replaces_symlink_to_dir(tmp_path, stage_module):
    ref_dir = tmp_path / "reference"
    ref_dir.mkdir()
    (ref_dir / "usr" / "lib").mkdir(parents=True)
    (ref_dir / "usr" / "lib" / "real.so").write_text("lib")
    os.symlink("lib", ref_dir / "usr" / "lib64")

    overlay_dir = tmp_path / "overlay"
    overlay_dir.mkdir()
    (overlay_dir / "usr" / "lib64").mkdir(parents=True)
    (overlay_dir / "usr" / "lib64" / "new.so").write_text("new lib")

    args = make_args(tmp_path, os.fspath(ref_dir), os.fspath(overlay_dir))
    stage_module.main(args)

    output = tmp_path / "output"
    assert (output / "usr/lib64/new.so").read_text() == "new lib"
    assert (output / "usr/lib64").is_dir()
    assert not (output / "usr/lib64").is_symlink()


def test_new_subdir_in_shared_parent(tmp_path, stage_module):
    ref = make_tree(tmp_path, "reference", {
        "/usr/lib/existing.so": "lib content",
    })
    overlay = make_tree(tmp_path, "overlay", {
        "/usr/lib/existing.so": "lib content",
        "/usr/lib/newpkg/data.txt": "new data",
        "/usr/lib/newpkg/sub/deep.txt": "deep",
    })
    args = make_args(tmp_path, ref, overlay)

    stage_module.main(args)

    output = tmp_path / "output"
    assert not (output / "usr/lib/existing.so").exists()
    assert (output / "usr/lib/newpkg/data.txt").read_text() == "new data"
    assert (output / "usr/lib/newpkg/sub/deep.txt").read_text() == "deep"


def test_deep_nested_only_changed_leaf_copied(tmp_path, stage_module):
    ref = make_tree(tmp_path, "reference", {
        "/usr/share/app/data/a.txt": "same",
        "/usr/share/app/data/b.txt": "same",
        "/usr/share/app/data/sub/c.txt": "same",
    })
    overlay = make_tree(tmp_path, "overlay", {
        "/usr/share/app/data/a.txt": "same",
        "/usr/share/app/data/b.txt": "same",
        "/usr/share/app/data/sub/c.txt": "changed",
    })
    args = make_args(tmp_path, ref, overlay)

    stage_module.main(args)

    output = tmp_path / "output"
    assert (output / "usr/share/app/data/sub/c.txt").read_text() == "changed"
    assert not (output / "usr/share/app/data/a.txt").exists()
    assert not (output / "usr/share/app/data/b.txt").exists()


@pytest.mark.parametrize("test_data,expected_err", [
    # good
    ({}, ""),
    ({"paths": ["/usr"]}, ""),
    ({"paths": ["/usr", "/opt"]}, ""),
    ({"exclude_paths": ["/usr/share/doc"]}, ""),
    ({"exclude_paths": ["/usr/share/doc", "/usr/share/man"]}, ""),
    ({"paths": ["/usr"], "exclude_paths": ["/usr/share/doc"]}, ""),
    # bad
    ({"paths": ["usr"]}, "does not match"),
    ({"exclude_paths": ["usr/share/doc"]}, "does not match"),
    ({"extra_field": True}, "'extra_field' was unexpected"),
])
def test_schema_validation(stage_schema, test_data, expected_err):
    test_input = {
        "type": STAGE_NAME,
    }
    if test_data:
        test_input["options"] = test_data
    res = stage_schema.validate(test_input)

    if expected_err == "":
        assert res.valid is True, f"err: {[e.as_dict() for e in res.errors]}"
    else:
        assert res.valid is False
        testutil.assert_jsonschema_error_contains(res, expected_err, expected_num_errs=1)
