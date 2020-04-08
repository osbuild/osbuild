"""SELinux utility functions"""

import subprocess

from typing import Dict, TextIO


def parse_config(config_file: TextIO):
    """Parse an SELinux configuration file"""
    config = {}
    for line in config_file:
        line = line.strip()
        if not line:
            continue
        if line.startswith('#'):
            continue
        k, v = line.split('=', 1)
        config[k.strip()] = v.strip()
    return config


def config_get_policy(config: Dict[str, str]):
    """Return the effective SELinux policy

    Checks if SELinux is enabled and if so returns the
    policy; otherwise `None` is returned.
    """
    enabled = config.get('SELINUX', 'disabled')
    if enabled not in ['enforcing', 'permissive']:
        return None
    return config.get('SELINUXTYPE', None)


def setfiles(spec_file: str, root: str, *paths):
    """Initialize the security context fields for `paths`

    Initialize the security context fields (extended attributes)
    on `paths` using the given specification in `spec_file`. The
    `root` argument determines the root path of the file system
    and the entries in `path` are interpreted as relative to it.
    Uses the setfiles(8) tool to actually set the contexts.
    """
    for path in paths:
        subprocess.run(["setfiles", "-F",
                        "-r", root,
                        spec_file,
                        f"{root}{path}"],
                       check=True)
