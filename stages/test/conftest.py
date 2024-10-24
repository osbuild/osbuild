import os
import pathlib
import subprocess
from types import ModuleType

import pytest

import osbuild.meta
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


@pytest.fixture
def stage_schema(request: pytest.FixtureRequest) -> osbuild.meta.Schema:
    """stage_schema is a fixture returns the schema for a stage module.

    This fixture may be indirectly parametrized with the stage schema version.
    If the schema version is not specified, the version "2" is assumed.
    The stage name must be defined in STAGE_NAME in the test module.
    """
    if hasattr(request, "param") and not isinstance(request.param, str):
        raise ValueError(
            "stage_schema fixture may be indirectly parametrized only with the stage schema version string")

    if not hasattr(request.module, "STAGE_NAME"):
        raise ValueError("stage_schema fixture must be used in a test module that defines STAGE_NAME")

    stage_name = request.module.STAGE_NAME
    schema_version = request.param if hasattr(request, "param") else "2"
    caller_dir = pathlib.Path(request.node.fspath).parent
    root = caller_dir.parent.parent
    mod_info = osbuild.meta.ModuleInfo.load(root, "Stage", stage_name)
    return osbuild.meta.Schema(mod_info.get_schema(version=schema_version), stage_name)


@pytest.fixture
def tmp_path_disk_full(tmp_path, tmp_path_disk_full_size):
    small_dir = tmp_path / "small-dir"
    small_dir.mkdir()
    subprocess.run(["mount",
                    "-t", "tmpfs",
                    "-o", f"size={tmp_path_disk_full_size}",
                    "tmpfs",
                    small_dir
                    ], check=True)
    yield small_dir
    subprocess.run(["umount", small_dir], check=True)
