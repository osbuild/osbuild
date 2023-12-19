"""
Test related utilities
"""
import os
import pathlib
import shutil


def has_executable(executable: str) -> bool:
    return shutil.which(executable) is not None


def assert_dict_has(v, keys, expected_value):
    for key in keys.split("."):
        assert key in v
        v = v[key]
    assert v == expected_value


def make_fake_tree(basedir: pathlib.Path, fake_content: dict):
    """Create a directory tree of files with content.

    Call it with:
        {"filename": "content", "otherfile": "content"}

    filename paths will have their parents created as needed, under tmpdir.
    """
    for path, content in fake_content.items():
        dirp, name = os.path.split(os.path.join(basedir, path.lstrip("/")))
        os.makedirs(dirp, exist_ok=True)
        with open(os.path.join(dirp, name), "w", encoding="utf-8") as fp:
            fp.write(content)


def make_fake_input_tree(tmpdir: pathlib.Path, fake_content: dict) -> str:
    """
    Wrapper around make_fake_tree for "input trees"
    """
    basedir = tmpdir / "tree"
    make_fake_tree(basedir, fake_content)
    return os.fspath(basedir)
