"""
Utility functions for reading and writing toml files.

Handles module imports for all supported versions (in a build root or on a host).
"""
import importlib
from types import ModuleType
from typing import Optional

# Different modules require different file mode (text vs binary)
_toml_modules = {
    "tomllib": {"mode": "rb"},  # stdlib since 3.11 (read-only)
    "tomli": {"mode": "rb"},  # EL9+
    "toml": {"mode": "r", "encoding": "utf-8"},  # older unmaintained lib, needed for backwards compatibility
    "pytoml": {"mode": "r", "encoding": "utf-8"},  # deprecated, needed for backwards compatibility (EL8 manifests)
}


_toml: Optional[ModuleType] = None
_rargs: dict = {}
for module, args in _toml_modules.items():
    try:
        _toml = importlib.import_module(module)
        _rargs = args
        break
    except ModuleNotFoundError:
        pass
else:
    raise ModuleNotFoundError("No toml module found: " + ", ".join(_toml_modules))

# Different modules require different file mode (text vs binary)
_tomlw_modules = {
    "tomli_w": {"mode": "wb"},  # EL9+
    "toml": {"mode": "w", "encoding": "utf-8"},  # older unmaintained lib, needed for backwards compatibility
    "pytoml": {"mode": "w", "encoding": "utf-8"},  # deprecated, needed for backwards compatibility (EL8 manifests)
}


_tomlw: Optional[ModuleType] = None
_wargs: dict = {}
for module, args in _tomlw_modules.items():
    try:
        _tomlw = importlib.import_module(module)
        _wargs = args
        break
    except ModuleNotFoundError:
        # Workaround for tomli_w being removed from c10s - use local copy then
        if module == "tomli_w":
            spec = importlib.util.spec_from_file_location('tomli_w', 'tomli_w.py')
            _tomlw = importlib.util.module_from_spec(spec)
        # allow importing without write support
        pass


def load_from_file(path):
    if _toml is None:
        raise RuntimeError("no toml module available")

    with open(path, **_rargs) as tomlfile:  # pylint: disable=unspecified-encoding
        return _toml.load(tomlfile)


def dump_to_file(data, path, header=""):
    if _tomlw is None:
        raise RuntimeError("no toml module available with write support")

    with open(path, **_wargs) as tomlfile:  # pylint: disable=unspecified-encoding
        if header:
            _write_comment(tomlfile, header)

        _tomlw.dump(data, tomlfile)


def _write_comment(f, comment: list):
    if not comment:
        return

    data = "\n".join(map(lambda c: f"# {c}", comment)) + "\n\n"
    if "b" in f.mode:
        f.write(data.encode())
    else:
        f.write(data)
