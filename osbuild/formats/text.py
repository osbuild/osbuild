"""Text formatting for output

Will output mostly text
"""
from typing import Dict
from ..pipeline import Manifest


RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"

FORMAT_KIND = ["OUT"]
VERSION = "text"
COMPATIBLE_RESULT_FORMATS = None


def print_text_error(error: str):
    print(f"{RESET}{BOLD}{RED}{error}{RESET}")


def print_result(manifest: Manifest, res: Dict, _info) -> Dict:
    if res["success"]:
        for name, pl in manifest.pipelines.items():
            print(f"{name + ':': <10}\t{pl.id}")
    print()
    print_text_error("failed")
