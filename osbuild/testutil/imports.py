#!/usr/bin/python3
"""
Import related utilities
"""
import importlib
import sys
from types import ModuleType

# Cache files will split the extension, this means that all pyc cache files
# looks like we get many clashing `org.osbuild.cpython-py311.pyc` files.
# Moreover, the cache bytecode invalidation is based on the timestamp (which
# is the same after git checkout) and the file size (which may be the same
# for two different files). This means that we can't rely on the cache files.
sys.dont_write_bytecode = True


def import_module_from_path(fullname, path: str) -> ModuleType:
    """import_module_from_path imports the given path as a python module

    This helper is useful when importing things that are not in the
    import path or have invalid python import filenames, e.g. all
    filenames in the stages/ dir of osbuild.

    Keyword arguments:
    fullname -- The absolute name of the module (can be arbitrary, used on in ModuleSpec.name)
    path     -- The full path to the python file
    """
    loader = importlib.machinery.SourceFileLoader(fullname, path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        # mypy warns that spec might be None so handle it
        raise ImportError(f"cannot import {fullname} from {path}, got None as the spec")
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod
