import os
import pathlib
from types import ModuleType

import pytest

from osbuild.testutil.imports import import_module_from_path


@pytest.fixture
def inputs_module(request: pytest.FixtureRequest) -> ModuleType:
    """inputs_module is a fixture that imports a stage module by its name
    defined in INPUTS_NAME in the test module.
    """
    if not hasattr(request.module, "INPUTS_NAME"):
        raise ValueError("inputs_module fixture must be used in a test module that defines INPUTS_NAME")

    inputs_name = request.module.INPUTS_NAME
    caller_dir = pathlib.Path(request.node.fspath).parent
    module_path = caller_dir.parent / inputs_name
    return import_module_from_path("inputs", os.fspath(module_path))
