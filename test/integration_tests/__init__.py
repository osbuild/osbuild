from typing import List

from .config import *

RESULTS: List[str] = []


def evaluate_test(test, arg=None, name=None):
    global RESULTS

    try:
        if arg:
            test(arg)
        else:
            test()

        result = f"{RESET}{BOLD}{name or test.__name__}: Success{RESET}"
        print(result)
        RESULTS += [result]
    except AssertionError as e:
        print(f"{RESET}{BOLD}{name or test.__name__}: {RESET}{RED}Fail{RESET}")
        print(e)


def rel_path(fname: str) -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), fname)


def print_results_again():
    global RESULTS
    for r in RESULTS:
        print(r)
