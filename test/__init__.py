from .constants import *


def evaluate_test(test, *args, name=None):
    try:
        test(*args)
        print(f"{RESET}{BOLD}{name or test.__name__}: Success{RESET}")
    except AssertionError as e:
        print(f"{RESET}{BOLD}{name or test.__name__}: {RESET}{RED}Fail{RESET}")
        print(e)


def rel_path(fname: str) -> str:
    return os.path.join(os.path.dirname(__file__), fname)
