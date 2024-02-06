import os
import pathlib
from types import ModuleType

import pytest

from osbuild.testutil.imports import import_module_from_path


@pytest.fixture
def sources_module(request: pytest.FixtureRequest) -> ModuleType:
    """sources_module is a fixture that imports a stage module by its name
    defined in SOURCES_NAME in the test module.
    """
    if not hasattr(request.module, "SOURCES_NAME"):
        raise ValueError("sources_module fixture must be used in a test module that defines SOURCES_NAME")

    sources_name = request.module.SOURCES_NAME
    caller_dir = pathlib.Path(request.node.fspath).parent
    module_path = caller_dir.parent / sources_name
    return import_module_from_path("sources", os.fspath(module_path))
