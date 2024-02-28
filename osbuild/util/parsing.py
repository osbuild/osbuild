"""Helpers related to parsing"""

import os
import re
from typing import Dict, Union
from urllib.parse import ParseResult, urlparse


def parse_size(s: str) -> Union[int, str]:
    """Parse a size string into a number or 'unlimited'.

    Supported suffixes: kB, kiB, MB, MiB, GB, GiB, TB, TiB
    """
    units = [
        (r'^\s*(\d+)\s*kB$', 1000, 1),
        (r'^\s*(\d+)\s*KiB$', 1024, 1),
        (r'^\s*(\d+)\s*MB$', 1000, 2),
        (r'^\s*(\d+)\s*MiB$', 1024, 2),
        (r'^\s*(\d+)\s*GB$', 1000, 3),
        (r'^\s*(\d+)\s*GiB$', 1024, 3),
        (r'^\s*(\d+)\s*TB$', 1000, 4),
        (r'^\s*(\d+)\s*TiB$', 1024, 4),
        (r'^\s*(\d+)$', 1, 1),
        (r'^unlimited$', "unlimited", 1),
    ]

    for pat, base, power in units:
        m = re.fullmatch(pat, s)
        if m:
            if isinstance(base, int):
                return int(m.group(1)) * base ** power
            if base == "unlimited":
                return "unlimited"

    raise TypeError(f"invalid size value: '{s}'")


def parse_mount(url: ParseResult, args: Dict) -> os.PathLike:
    """
    Parses the mount URL to extract the root path.

    Parameters:
    - url (ParseResult): The ParseResult object obtained from urlparse.
    - args (Dict): A dictionary containing arguments including mounts information.
    """
    name = url.netloc
    if name:
        root = args["mounts"].get(name, {}).get("path")
        if not root:
            raise ValueError(f"Unknown mount '{name}'")
    else:
        root = args["paths"]["mounts"]

    return root


def parse_input(url: ParseResult, args: Dict) -> os.PathLike:
    """
    Parses the input URL to extract the root path.

    Parameters:
    - url (ParseResult): The ParseResult object obtained from urlparse.
    - args (Dict): A dictionary containing arguments including mounts information.
    """
    name = url.netloc
    root = args["inputs"].get(name, {}).get("path")
    if root is None:
        raise ValueError(f"Unknown input '{name}'")

    return root


def parse_location(location: str, args: Dict) -> str:
    """
    Parses the location URL to derive the corresponding file path.

    Parameters:
    - location (str): The location URL to be parsed.
    - args (Dict): A dictionary containing arguments including tree and mount information.
    """

    url = urlparse(location)

    scheme = url.scheme
    if scheme == "tree":
        root = args["tree"]
    elif scheme == "mount":
        root = parse_mount(url, args)
    elif scheme == "input":
        root = parse_input(url, args)
    else:
        raise ValueError(f"Unsupported scheme '{scheme}'")

    assert url.path.startswith("/")

    path = os.path.relpath(url.path, "/")
    path = os.path.join(root, path)
    path = os.path.normpath(path)

    if url.path.endswith("/"):
        path = os.path.join(path, ".")

    return path
