"""OSBuild Main

This specifies the entrypoint of the osbuild module when run as executable. For
compatibility we will continue to run the CLI.
"""

import os
import sys

from osbuild.main_cli import _reexec_in_userns
from osbuild.main_cli import osbuild_cli as main

if __name__ == "__main__":
    if os.getuid() != 0:
        # Re-exec in a user namespace when possible; returns the child's exit
        # status to propagate, or None to fall back to the normal code path.
        r = _reexec_in_userns()
        if r is not None:
            sys.exit(r)
    r = main()
    sys.exit(r)
