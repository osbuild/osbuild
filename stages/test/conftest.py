import os
import pathlib
from types import ModuleType

import pytest

from osbuild.testutil.imports import import_module_from_path


@pytest.fixture
def stage_module(request: pytest.FixtureRequest) -> ModuleType:
    """stage_module is a fixture that imports a stage module by its name
    defined in STAGE_NAME in the test module.
    """
    if not hasattr(request.module, "STAGE_NAME"):
        raise ValueError("stage_module fixture must be used in a test module that defines STAGE_NAME")

    stage_name = request.module.STAGE_NAME
    caller_dir = pathlib.Path(request.node.fspath).parent
    module_path = caller_dir.parent / stage_name
    return import_module_from_path("stage", os.fspath(module_path))
