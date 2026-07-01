"""SELinux utility functions"""

import errno
import os
import subprocess
from typing import Dict, List, Optional, TextIO

from osbuild.util.chroot import Chroot

# Extended attribute name for SELinux labels
XATTR_NAME_SELINUX = b"security.selinux"


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


def chroot_rel_path(path: str, root: str) -> str:
    path = os.fspath(path)
    root = os.fspath(root)
    if path == root:
        return "/"
    # if path belongs to root, the aim is to get location of the path from root
    prefix = root + os.sep
    if path.startswith(prefix):
        rel = os.path.relpath(path, root)
        if rel == ".":
            return "/"
        return f"/{rel}"
    return path


def setfiles_binary_in_tree(root: str) -> str:
    setfiles_location = "/usr/bin/setfiles"
    if os.path.isfile(os.path.join(root, setfiles_location.lstrip("/"))):
        return setfiles_location
    raise RuntimeError(
        f"setfiles not found at {root} (try using setfiles_from='host')"
    )


def setfiles(
        spec_file: str,
        root: str,
        *paths,
        exclude_paths: Optional[List[str]] = None,
        setfiles_from: str = "host") -> None:
    """Initialize the security context fields for `paths`

    Initialize the security context fields (extended attributes)
    on `paths` using the given specification in `spec_file`. The
    `root` argument determines the root path of the file system
    and the entries in `path` are interpreted as relative to it.
    Uses the setfiles(8) tool to actually set the contexts.
    Paths can be excluded via the exclude_paths argument.

    With ``setfiles_from='tree'``, setfiles is executed from the tree
    via chroot(2),.
    """
    if setfiles_from not in ["host", "tree"]:
        raise ValueError(f"invalid setfiles_from: {setfiles_from}")

    if exclude_paths is None:
        exclude_paths = []

    if setfiles_from == "host":
        exclude_paths_args = []
        for p in exclude_paths:
            exclude_paths_args.extend(["-e", p])

        for path in paths:
            subprocess.run(["setfiles", "-F",
                            "-r", root,
                            *exclude_paths_args,
                            spec_file,
                            f"{root}{path}"],
                           check=True)
        return

    # Changing chroot means we need to change relative path
    # to a specfile and excluded paths.
    setfiles_bin = setfiles_binary_in_tree(root)
    spec = chroot_rel_path(spec_file, root)
    exclude_paths_args = []
    for p in exclude_paths:
        exclude_paths_args.extend(["-e", chroot_rel_path(p, root)])

    with Chroot(root) as chroot:
        for path in paths:
            chroot.run([setfiles_bin, "-F",
                        *exclude_paths_args,
                        spec,
                        path],
                       check=True)


def getfilecon(path: str) -> str:
    """Get the security context associated with `path`"""
    label = os.getxattr(path, XATTR_NAME_SELINUX,
                        follow_symlinks=False)
    return label.decode().strip('\n\0')


def setfilecon(path: str, context: str) -> None:
    """
    Set the security context associated with `path`

    Like `setfilecon`(3), but does not attempt to translate
    the context via `selinux_trans_to_raw_context`.
    """

    try:
        os.setxattr(path, XATTR_NAME_SELINUX,
                    context.encode(),
                    follow_symlinks=True)
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
