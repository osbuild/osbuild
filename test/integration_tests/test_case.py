from dataclasses import dataclass
from enum import Enum
from typing import List, Callable, Any

from . import evaluate_test, rel_path
from .build import run_osbuild
from .run import boot_image, extract_image


class IntegrationTestType(Enum):
    EXTRACT=0
    BOOT_WITH_QEMU=1


@dataclass
class IntegrationTestCase:
    name: str
    pipeline: str
    output_image: str
    test_cases: List[Callable[[Any], None]]
    type: IntegrationTestType

    def run(self):
        run_osbuild(rel_path(f"pipelines/{self.pipeline}"))
        if self.type == IntegrationTestType.BOOT_WITH_QEMU:
            self.boot_and_run()
        else:
            self.extract_and_run()

    def boot_and_run(self):
        with boot_image(self.output_image):
            for test in self.test_cases:
                evaluate_test(test)

    def extract_and_run(self):
        with extract_image(self.output_image) as fstree:
            for test in self.test_cases:
                evaluate_test(lambda: test(fstree), name=test.__name__)
