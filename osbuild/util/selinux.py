"""SELinux utility functions"""

import errno
import os
import subprocess
from typing import Dict, TextIO

# Extended attribute name for SELinux labels
XATTR_NAME_SELINUX = b"security.selinux"


def parse_config(config_file: TextIO):
    """Parse an SELinux configuration file"""
    config = {}
    for line in config_file:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        k, v = line.split("=", 1)
        config[k.strip()] = v.strip()
    return config


def config_get_policy(config: Dict[str, str]):
    """Return the effective SELinux policy

    Checks if SELinux is enabled and if so returns the
    policy; otherwise `None` is returned.
    """
    enabled = config.get("SELINUX", "disabled")
    if enabled not in ["enforcing", "permissive"]:
        return None
    return config.get("SELINUXTYPE", None)


def setfiles(spec_file: str, root: str, *paths):
    """Initialize the security context fields for `paths`

    Initialize the security context fields (extended attributes)
    on `paths` using the given specification in `spec_file`. The
    `root` argument determines the root path of the file system
    and the entries in `path` are interpreted as relative to it.
    Uses the setfiles(8) tool to actually set the contexts.
    """
    for path in paths:
        subprocess.run(["setfiles", "-F", "-r", root, spec_file, f"{root}{path}"], check=True)


def getfilecon(path: str) -> str:
    """Get the security context associated with `path`"""
    label = os.getxattr(path, XATTR_NAME_SELINUX, follow_symlinks=False)
    return label.decode().strip("\n\0")


def setfilecon(path: str, context: str) -> None:
    """
    Set the security context associated with `path`

    Like `setfilecon`(3), but does not attempt to translate
    the context via `selinux_trans_to_raw_context`.
    """

    try:
        os.setxattr(path, XATTR_NAME_SELINUX, context.encode(), follow_symlinks=True)
    except OSError as err:
        # in case we get a not-supported error, check if
        # the context we want to set is already set and
        # ignore the error in that case. This follows the
        # behavior of `setfilecon(3)`.
        if err.errno == errno.ENOTSUP:
            have = getfilecon(path)
            if have == context:
                return
        raise
