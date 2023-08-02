"""Helpers related to parsing"""

import re
from typing import Union


def parse_size(s: str) -> Union[int, str]:
    """Parse a size string into a number or 'unlimited'.

    Supported suffixes: kB, kiB, MB, MiB, GB, GiB, TB, TiB
    """
    units = [
        (r"^\s*(\d+)\s*kB$", 1000, 1),
        (r"^\s*(\d+)\s*KiB$", 1024, 1),
        (r"^\s*(\d+)\s*MB$", 1000, 2),
        (r"^\s*(\d+)\s*MiB$", 1024, 2),
        (r"^\s*(\d+)\s*GB$", 1000, 3),
        (r"^\s*(\d+)\s*GiB$", 1024, 3),
        (r"^\s*(\d+)\s*TB$", 1000, 4),
        (r"^\s*(\d+)\s*TiB$", 1024, 4),
        (r"^\s*(\d+)$", 1, 1),
        (r"^unlimited$", "unlimited", 1),
    ]

    for pat, base, power in units:
        m = re.fullmatch(pat, s)
        if m:
            if isinstance(base, int):
                return int(m.group(1)) * base**power
            if base == "unlimited":
                return "unlimited"

    raise TypeError(f"invalid size value: '{s}'")
