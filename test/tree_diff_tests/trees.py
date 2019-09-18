import contextlib
import json
import os
from dataclasses import dataclass

import osbuild
from test import rel_path, OBJECTS, OUTPUT_DIR
from test.build import run_osbuild
from test.tree_diff_tests.mount import mount_image, ImageType


@dataclass
class Tree:
    pipeline: str
    build_pipeline: str

    def build(self):
        run_osbuild(self.get_relative_pipeline(), self.build_pipeline)

    def get_relative_pipeline(self):
        return rel_path(os.path.join("pipelines", self.pipeline))

    def has_same_pipeline_as(self, other: 'Tree'):
        return self.pipeline == other.pipeline


@dataclass
class TreeFromObjectStore(Tree):
    @contextlib.contextmanager
    def mount(self):
        with open(self.get_relative_pipeline()) as f:
            pipeline = osbuild.load(json.load(f))
            pipeline_id = pipeline.get_id()
            yield os.path.join(OBJECTS, "refs", pipeline_id)


@dataclass
class TreeFromImage(Tree):
    output_image: str
    output_image_type: ImageType

    @contextlib.contextmanager
    def mount(self):
        with mount_image(os.path.join(OUTPUT_DIR, self.output_image), self.output_image_type) as image:
            yield image
