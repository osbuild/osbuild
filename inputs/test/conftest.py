import inspect
import os
import pathlib
from types import ModuleType

import pytest

from osbuild import inputs, testutil
from osbuild.testutil.imports import import_module_from_path


@pytest.fixture(name="inputs_module")
def inputs_module_fixture(request: pytest.FixtureRequest) -> ModuleType:
    """inputs_module is a fixture that imports a stage module by its name
    defined in INPUTS_NAME in the test module.
    """
    if not hasattr(request.module, "INPUTS_NAME"):
        raise ValueError("inputs_module fixture must be used in a test module that defines INPUTS_NAME")

    inputs_name = request.module.INPUTS_NAME
    caller_dir = pathlib.Path(request.node.fspath).parent
    module_path = caller_dir.parent / inputs_name
    return import_module_from_path("inputs", os.fspath(module_path))


@pytest.fixture
def inputs_service(inputs_module) -> ModuleType:
    """inputs_service is a fixture that imports a inputs module by its name
    defined in INPUTS_NAME in the test module and returns a InputService
    """
    service_cls = None
    for memb in inspect.getmembers(
            inputs_module,
            predicate=lambda obj: inspect.isclass(obj) and issubclass(
                obj, inputs.InputService)):
        if service_cls:
            raise ValueError(f"already have {service_cls}, also found {memb}")
        service_cls = memb[1]
    fd = testutil.make_fake_service_fd()
    srv_obj = service_cls.from_args(["--service-fd", str(fd)])
    return srv_obj
