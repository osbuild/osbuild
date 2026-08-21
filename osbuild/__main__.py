"""OSBuild Main

This specifies the entrypoint of the osbuild module when run as executable. For
compatibility we will continue to run the CLI.
"""

import sys

from osbuild.main_cli import osbuild_cli as main

if __name__ == "__main__":
    r = main()
    sys.exit(r)
