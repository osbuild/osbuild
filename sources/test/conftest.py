import os
import pathlib
from types import ModuleType

import pytest

import osbuild.meta
from osbuild import sources, testutil
from osbuild.testutil.imports import import_module_from_path


@pytest.fixture(name="sources_module")
def sources_module_fixture(request: pytest.FixtureRequest) -> ModuleType:
    """sources_module is a fixture that imports a stage module by its name
    defined in SOURCES_NAME in the test module.
    """
    if not hasattr(request.module, "SOURCES_NAME"):
        raise ValueError("sources_module fixture must be used in a test module that defines SOURCES_NAME")

    sources_name = request.module.SOURCES_NAME
    caller_dir = pathlib.Path(request.node.fspath).parent
    module_path = caller_dir.parent / sources_name
    return import_module_from_path("sources", os.fspath(module_path))


@pytest.fixture
def sources_service(sources_module) -> ModuleType:
    """sources_service is a fixture that imports a sources module by its name
    defined in SOURCES_NAME in the test module and returns a SourcesService
    """
    service_cls = testutil.find_one_subclass_in_module(sources_module, sources.SourceService)
    fd = testutil.make_fake_service_fd()
    srv_obj = service_cls.from_args(["--service-fd", str(fd)])
    return srv_obj


@pytest.fixture
def sources_schema(request: pytest.FixtureRequest) -> osbuild.meta.Schema:
    """
    source_schema is a fixture returns the schema for a sources module.
    """
    if hasattr(request, "param") and not isinstance(request.param, str):
        raise ValueError(
            "sources_schema fixture may be indirectly parametrized only with the sources schema version string")

    if not hasattr(request.module, "SOURCES_NAME"):
        raise ValueError("sources_schema fixture must be used in a test module that defines SOURCES_NAME")

    sources_name = request.module.SOURCES_NAME
    schema_version = request.param if hasattr(request, "param") else "2"
    caller_dir = pathlib.Path(request.node.fspath).parent
    root = caller_dir.parent.parent
    mod_info = osbuild.meta.ModuleInfo.load(root, "Source", sources_name)
    return osbuild.meta.Schema(mod_info.get_schema(version=schema_version), sources_name)
