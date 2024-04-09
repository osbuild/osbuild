import os
import pathlib
from types import ModuleType

import pytest

from osbuild import mounts, testutil
from osbuild.testutil.imports import import_module_from_path


@pytest.fixture(name="mounts_module")
def mounts_module_fixture(request: pytest.FixtureRequest) -> ModuleType:
    """mounts_module is a fixture that imports a stage module by its name
    defined in MOUNTS_NAME in the test module.
    """
    if not hasattr(request.module, "MOUNTS_NAME"):
        raise ValueError("mounts_module fixture must be used in a test module that defines MOUNTS_NAME")

    mounts_name = request.module.MOUNTS_NAME
    caller_dir = pathlib.Path(request.node.fspath).parent
    module_path = caller_dir.parent / mounts_name
    return import_module_from_path("mounts", os.fspath(module_path))


@pytest.fixture
def mounts_service(mounts_module) -> ModuleType:
    """mounts_service is a fixture that imports a mounts module by its name
    defined in MOUNTS_NAME in the test module and returns a MountsService
    """
    service_cls = testutil.find_one_subclass_in_module(mounts_module, mounts.MountService)
    fd = testutil.make_fake_service_fd()
    srv_obj = service_cls.from_args(["--service-fd", str(fd)])
    return srv_obj
