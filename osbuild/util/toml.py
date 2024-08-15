"""
Utility functions for reading and writing toml files.

Handles module imports for all supported versions (in a build root or on a host).
"""
import importlib

# Different modules require different file mode (text vs binary)
toml_modules = {
    "tomllib": "rb",  # stdlib since 3.11 (read-only)
    "tomli": "rb",  # EL9+
    "toml": "r",  # older unmaintained lib, needed for backwards compatibility with existing EL9 and Fedora manifests
    "pytoml": "r",  # deprecated, needed for backwards compatibility (EL8 manifests)
}


toml = None
rmode: str = None
for module, mode in toml_modules.items():
    try:
        toml = importlib.import_module(module)
        rmode = mode
        break
    except ModuleNotFoundError:
        pass
else:
    raise ModuleNotFoundError("No toml module found: " + ", ".join(toml_modules))

# Different modules require different file mode (text vs binary)
tomlw_modules = {
    "tomli_w": "wb",  # EL9+
    "toml": "w",  # older unmaintained lib, needed for backwards compatibility with existing EL9 and Fedora manifests
    "pytoml": "w",  # deprecated, needed for backwards compatibility (EL8 manifests)
}


tomlw = None
wmode: str = None
for module, mode in tomlw_modules.items():
    try:
        tomlw = importlib.import_module(module)
        wmode = mode
        break
    except ModuleNotFoundError:
        # allow importing without write support
        pass


def load_from_file(path):
    with open(path, rmode) as tomlfile:
        return toml.load(tomlfile)


def dump_to_file(data, path, header=""):
    if tomlw is None:
        raise RuntimeError("no toml module available with write support")

    with open(path, wmode) as tomlfile:
        if header:
            _write_comment(tomlfile, header)

        tomlw.dump(data, tomlfile)


def _write_comment(f, comment: list):
    if not comment:
        return

    data = "\n".join(map(lambda c: f"# {c}", comment)) + "\n\n"
    if "b" in f.mode:
        f.write(data.encode())
    else:
        f.write(data)
