from .config import *


def evaluate_test(test, arg=None, name=None):
    try:
        if arg:
            test(arg)
        else:
            test()

        print(f"{RESET}{BOLD}{name or test.__name__}: Success{RESET}")
    except AssertionError as e:
        print(f"{RESET}{BOLD}{name or test.__name__}: {RESET}{RED}Fail{RESET}")
        print(e)


def rel_path(fname: str) -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), fname)
