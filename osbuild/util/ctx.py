"""ContextManager Utilities

This module implements helpers around python context-managers, with-statements,
and RAII. It is meant as a supplement to `contextlib` from the python standard
library.
"""

import contextlib

__all__ = [
    "suppress_oserror",
]


@contextlib.contextmanager
def suppress_oserror(*errnos):
    """Suppress OSError Exceptions

    This is an extension to `contextlib.suppress()` from the python standard
    library. It catches any `OSError` exceptions and suppresses them. However,
    it only catches the exceptions that match the specified error numbers.

    Parameters
    ----------
    errnos
        A list of error numbers to match on. If none are specified, this
        function has no effect.
    """

    try:
        yield
    except OSError as e:
        if e.errno not in errnos:
            raise e
