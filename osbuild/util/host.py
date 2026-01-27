"""
Utility functions that only run on the host (osbuild internals or host modules like sources).

These should not be used by stages or code that runs in the build root.
"""


def get_container_storage():
    """
    Read the host storage configuration.
    """

    # In some cases (for example in CI) the toml module is not available.
    # In such cases, we error at use, not at import time to avoid breaking things.

    try:
        # pylint: disable=import-outside-toplevel
        from osbuild.util import toml
    except ImportError as e:
        raise FileNotFoundError("could not find toml parser to read container storage configuration") from e

    config_paths = ("/etc/containers/storage.conf", "/usr/share/containers/storage.conf")
    for conf_path in config_paths:
        try:
            return toml.load_from_file(conf_path)
        except FileNotFoundError:
            pass

    raise FileNotFoundError(f"could not find container storage configuration in any of {config_paths}")
