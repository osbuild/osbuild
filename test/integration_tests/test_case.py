import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Callable, Any

from test import evaluate_test, rel_path
from test.build import run_osbuild
from .run import run_image, extract_image


class IntegrationTestType(Enum):
    EXTRACT=0
    BOOT_WITH_QEMU=1


@dataclass
class IntegrationTestCase:
    name: str
    pipeline: str
    build_pipeline: str
    output_image: str
    test_cases: List[Callable[[Any], None]]
    type: IntegrationTestType

    def run(self):
        logging.info(f"Running integration test {self.name}")
        run_osbuild(rel_path(f"pipelines/{self.pipeline}"), self.build_pipeline)
        if self.type == IntegrationTestType.BOOT_WITH_QEMU:
            self.run_and_test()
        else:
            self.extract_and_test()

    def run_and_test(self):
        r = run_image(self.output_image)
        for test in self.test_cases:
            evaluate_test(test, r.stdout)

    def extract_and_test(self):
        with extract_image(self.output_image) as fstree:
            for test in self.test_cases:
                evaluate_test(lambda: test(fstree), name=test.__name__)
