"""SELinux utility functions"""

import errno
import os
import re
import subprocess
from typing import Dict, List, Optional, Set, TextIO

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


def is_selinux_enabled() -> bool:
    """Check whether SELinux is enabled on the running system."""
    return os.path.exists("/sys/fs/selinux/context")


def is_known_type(type_name: str) -> bool:
    """Check if an SELinux type exists in the kernel's loaded policy."""
    try:
        # This is the same implementation as security_check_context()
        fd = os.open("/sys/fs/selinux/context", os.O_WRONLY)
        try:
            os.write(fd, f"system_u:object_r:{type_name}:s0".encode())
            return True
        except OSError:
            return False
        finally:
            os.close(fd)
    except OSError:
        return False


def parse_file_contexts(path: str) -> Dict[str, List[str]]:
    """Parse a file_contexts file and return a mapping of type -> list of path patterns."""
    type_patterns: Dict[str, List[str]] = {}
    with open(path, encoding="utf8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # each line is `pathname_regexp  [file_type]  security_context`, whitespace separated
            parts = line.split()
            context = parts[-1]
            # Ignore no-context rules
            if context == "<<none>>":
                continue
            fields = context.split(":")
            if len(fields) >= 3:
                type_patterns.setdefault(fields[2], []).append(parts[0])
    return type_patterns


def find_unknown_types_used(file_contexts: str, root: str,
                            exclude_paths: Optional[List[str]] = None) -> Set[str]:
    """Find unknown SELinux types whose file_contexts patterns match files in the tree."""
    exclude = set(exclude_paths or [])
    type_patterns = parse_file_contexts(file_contexts)

    # Compile a regexp that matches for each unknown type a list of
    # all pathname patterns that would be used by it.
    unknown_regexes = {}
    for t, patterns in type_patterns.items():
        if not is_known_type(t):
            alt = "|".join(f"(?:{p})" for p in patterns)
            try:
                unknown_regexes[t] = re.compile(f"^(?:{alt})$")
            except re.error:
                continue

    if not unknown_regexes:
        return set()

    # Walk the tree and see if any path matches one of the
    # regexps for an unknown regexp.
    used = set()
    prefix_len = len(root)
    for dirpath, dirnames, filenames in os.walk(root):
        # Don't descend into excluded directories; they won't be relabeled.
        dirnames[:] = [d for d in dirnames if os.path.join(dirpath, d) not in exclude]
        for name in [dirpath] + [os.path.join(dirpath, f) for f in filenames + dirnames]:
            if name in exclude:
                continue
            logical = name[prefix_len:]
            if not logical:
                logical = "/"
            for t, rx in list(unknown_regexes.items()):
                if rx.match(logical):
                    used.add(t)
                    del unknown_regexes[t]  # No need to look for this type again
            if not unknown_regexes:
                return used  # Found all, return early
    return used


def setfiles(spec_file: str, root: str, *paths, exclude_paths: Optional[List[str]] = None) -> None:
    """Initialize the security context fields for `paths`

    Initialize the security context fields (extended attributes)
    on `paths` using the given specification in `spec_file`. The
    `root` argument determines the root path of the file system
    and the entries in `path` are interpreted as relative to it.
    Uses the setfiles(8) tool to actually set the contexts.
    Paths can be excluded via the exclude_paths argument.
    """
    if exclude_paths is None:
        exclude_paths = []
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
