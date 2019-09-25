import tempfile
import os


EXPECTED_TIME_TO_BOOT = 60  # seconds
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
OBJECTS = os.environ.get("OBJECTS", ".osbuild-test")
OSBUILD = os.environ.get("OSBUILD", "python3 -m osbuild --libdir .").split(' ')
