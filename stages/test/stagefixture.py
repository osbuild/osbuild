import os

import pytest

from osbuild.testutil.imports import import_module_from_path


@pytest.fixture(name="stage")
def stagefixture(request):
    stage_name = request.module.STAGE
    stage_path = os.path.join(os.path.dirname(__file__), f"../{stage_name}")
    stage = import_module_from_path("xz_stage", stage_path)
    return stage
