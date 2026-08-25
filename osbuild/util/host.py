"""
Utility functions that only run on the host (osbuild internals or host modules like sources).

These should not be used by stages or code that runs in the build root.
"""

import os


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
    conf = None
    for conf_path in config_paths:
        try:
            conf = toml.load_from_file(conf_path)
            break
        except FileNotFoundError:
            pass

    # Handle CONTAINERS_GRAPHROOT and CONTAINERS_RUNROOT env var overrides, as set by
    # `podman unshare`.
    env_graphroot = os.environ.get("CONTAINERS_GRAPHROOT")
    env_runroot = os.environ.get("CONTAINERS_RUNROOT")

    if env_graphroot:
        conf = conf or {}
        storage = conf.setdefault("storage", {})
        storage["graphroot"] = env_graphroot
        if env_runroot:
            storage["runroot"] = env_runroot
        return conf

    if conf:
        return conf

    raise FileNotFoundError(f"could not find container storage configuration in any of {config_paths}")
