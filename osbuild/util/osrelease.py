"""OS-Release Information

This module implements handlers for the `/etc/os-release` type of files. The
related documentation can be found in `os-release(5)`.
"""

import os
import shlex

# The default paths where os-release is located, as per os-release(5)
DEFAULT_PATHS = [
    "/etc/os-release",
    "/usr/lib/os-release"
]


def parse_files(*paths):
    """Read Operating System Information from `os-release`

    This creates a dictionary with information describing the running operating
    system. It reads the information from the path array provided as `paths`.
    The first available file takes precedence. It must be formatted according
    to the rules in `os-release(5)`.
    """
    osrelease = {}

    path = next((p for p in paths if os.path.exists(p)), None)
    if path:
        with open(path, encoding="utf8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line[0] == "#":
                    continue
                key, value = line.split("=", 1)
                split_value = shlex.split(value)
                if not split_value or len(split_value) > 1:
                    raise ValueError(f"Key '{key}' has an empty value or more than one token: {value}")
                osrelease[key] = split_value[0]

    return osrelease


def describe_os(*paths):
    """Read the Operating System Description from `os-release`

    This creates a string describing the running operating-system name and
    version. It uses `parse_files()` underneath to acquire the requested
    information.

    The returned string uses the format `${ID}${VERSION_ID}` with all dots
    stripped.
    """
    osrelease = parse_files(*paths)

    # Fetch `ID` and `VERSION_ID`. Defaults are defined in `os-release(5)`.
    osrelease_id = osrelease.get("ID", "linux")
    osrelease_version_id = osrelease.get("VERSION_ID", "")

    return osrelease_id + osrelease_version_id.replace(".", "")
