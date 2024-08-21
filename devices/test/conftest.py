import os
import pathlib
from types import ModuleType

import pytest

from osbuild import devices, testutil
from osbuild.testutil.imports import import_module_from_path


@pytest.fixture(name="devices_module")
def devices_module_fixture(request: pytest.FixtureRequest) -> ModuleType:
    """devices_module is a fixture that imports a stage module by its name
    defined in DEVICES_NAME in the test module.
    """
    if not hasattr(request.module, "DEVICES_NAME"):
        raise ValueError("devices_module fixture must be used in a test module that defines DEVICES_NAME")

    devices_name = request.module.DEVICES_NAME
    caller_dir = pathlib.Path(request.node.fspath).parent
    module_path = caller_dir.parent / devices_name
    return import_module_from_path("devices", os.fspath(module_path))


@pytest.fixture
def devices_service(devices_module) -> ModuleType:
    """devices_service is a fixture that imports a devices module by its name
    defined in DEVICES_NAME in the test module and returns a Deviceservice
    """
    service_cls = testutil.find_one_subclass_in_module(devices_module, devices.DeviceService)
    fd = testutil.make_fake_service_fd()
    srv_obj = service_cls.from_args(["--service-fd", str(fd)])
    return srv_obj
