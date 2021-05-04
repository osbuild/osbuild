"""Path handling utility functions"""
import os.path

from .types import PathLike


def in_tree(path: PathLike, tree: PathLike, must_exist=False) -> bool:
    """Return whether the canonical location of 'path' is under 'tree'.
    If 'must_exist' is True, the file must also exist for the check to succeed.
    """
    path = os.path.abspath(path)
    if path.startswith(tree):
        return os.path.exists(path) or not must_exist
    return False
