"""
Test related utilities
"""
import os
import shutil


def has_executable(executable: str) -> bool:
    return shutil.which(executable) is not None


def assert_dict_has(v, keys, expected_value):
    for key in keys.split("."):
        assert key in v
        v = v[key]
    assert v == expected_value


def make_fake_input_tree(tmpdir, fake_content: dict) -> str:
    """Create a directory tree of files with content.

    Call it with:
        {"filename": "content", "otherfile": "content"}

    filename paths will have their parents created as needed, under tmpdir.
    """
    basedir = os.path.join(tmpdir, "tree")
    for path, content in fake_content.items():
        dirp, name = os.path.split(os.path.join(basedir, path.lstrip("/")))
        os.makedirs(dirp, exist_ok=True)
        with open(os.path.join(dirp, name), "w", encoding="utf-8") as fp:
            fp.write(content)
    return basedir
