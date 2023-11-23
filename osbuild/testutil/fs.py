"""
Fake filesystem content
"""
import os


def make_fs_tree(basedir, fake_content: dict) -> str:
    """
    make_fs_tree creates a filesystem tree based on the fake_content dict.

    Usage:
    make_fs_tree("/tmp/", {"/test-dir/test-file": "file-content", ...})
    """
    for path, content in fake_content.items():
        dirp, name = os.path.split(os.path.join(basedir, path.lstrip("/")))
        os.makedirs(dirp, exist_ok=True)
        if content is not None:
            with open(os.path.join(dirp, name), "w", encoding="utf-8") as fp:
                fp.write(content)
    return basedir
