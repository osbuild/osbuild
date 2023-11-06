#
# Tests for the 'osbuild.util.testutil' module.
#
import os.path
import tempfile

import pytest

from osbuild.testutil.imports import import_module_from_path


canary = "import-went-okay"


def test_import_module_from_path_happy():
    mod = import_module_from_path("myself", __file__)
    assert mod.canary == "import-went-okay"
