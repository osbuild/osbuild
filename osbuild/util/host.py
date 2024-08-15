"""
Utility functions that only run on the host (osbuild internals or host modules like sources).

These should not be used by stages or code that runs in the build root.
"""
from osbuild.util import toml


def get_container_storage():
    """
    Read the host storage configuration.
    """
    config_paths = ("/etc/containers/storage.conf", "/usr/share/containers/storage.conf")
    for conf_path in config_paths:
        try:
            return toml.load_from_file(conf_path)
        except FileNotFoundError:
            pass

    raise FileNotFoundError(f"could not find container storage configuration in any of {config_paths}")
