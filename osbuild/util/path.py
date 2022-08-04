"""Path handling utility functions"""
import os


def in_tree(path: str, tree: str, must_exist: bool = False) -> bool:
    """Return whether the canonical location of 'path' is under 'tree'.
    If 'must_exist' is True, the file must also exist for the check to succeed.
    """
    path = os.path.abspath(path)
    if path.startswith(tree):
        return not must_exist or os.path.exists(path)
    return False
