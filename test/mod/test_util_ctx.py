#
# Tests for the 'osbuild.util.ctx' module.
#

import errno
import unittest

from osbuild.util import ctx


class TestUtilCtx(unittest.TestCase):
    def test_suppress_oserror(self):
        #
        # Verify the `suppress_oserror()` function.
        #

        # Empty list and empty statement is a no-op.
        with ctx.suppress_oserror():
            pass

        # Single errno matches raised errno.
        with ctx.suppress_oserror(errno.EPERM):
            raise OSError(errno.EPERM, "Operation not permitted")

        # Many errnos match raised errno regardless of their order.
        with ctx.suppress_oserror(errno.EPERM, errno.ENOENT, errno.ESRCH):
            raise OSError(errno.EPERM, "Operation not permitted")
        with ctx.suppress_oserror(errno.ENOENT, errno.EPERM, errno.ESRCH):
            raise OSError(errno.EPERM, "Operation not permitted")
        with ctx.suppress_oserror(errno.ENOENT, errno.ESRCH, errno.EPERM):
            raise OSError(errno.EPERM, "Operation not permitted")

        # Empty list re-raises exceptions.
        with self.assertRaises(OSError):
            with ctx.suppress_oserror():
                raise OSError(errno.EPERM, "Operation not permitted")

        # Non-matching lists re-raise exceptions.
        with self.assertRaises(OSError):
            with ctx.suppress_oserror(errno.ENOENT):
                raise OSError(errno.EPERM, "Operation not permitted")
            with ctx.suppress_oserror(errno.ENOENT, errno.ESRCH):
                raise OSError(errno.EPERM, "Operation not permitted")
