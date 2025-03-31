"""Handling of experimental environment flags"""

import os
from typing import Any, Dict


def _experimental_env_map() -> Dict[str, Any]:
    env_map: Dict[str, Any] = {}
    for exp_opt in os.environ.get("OSBUILD_EXPERIMENTAL", "").split(","):
        l = exp_opt.split("=", maxsplit=1)
        if len(l) == 1:
            env_map[exp_opt] = "true"
        elif len(l) == 2:
            env_map[l[0]] = l[1]
    return env_map


def get_bool(option: str) -> bool:
    env_map = _experimental_env_map()
    opt = env_map.get(option, "")
    # sadly python as no strconv.ParseBool() like golang so we roll our own
    if opt.upper() in {"1", "T", "TRUE"}:
        return True
    if opt.upper() in {"", "0", "F", "FALSE"}:
        return False
    raise RuntimeError(f"unsupport bool val {opt}")


def get_string(option: str) -> str:
    env_map = _experimental_env_map()
    return str(env_map.get(option, ""))
