import tempfile
import os


EXPECTED_TIME_TO_BOOT = 60  # seconds
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
OBJECTS = os.environ.get("OBJECTS", tempfile.mkdtemp(prefix="osbuild-"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", tempfile.mkdtemp(prefix="osbuild-"))
OSBUILD = os.environ.get("OSBUILD", "osbuild").split(' ')
