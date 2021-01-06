# Version 1 of the manifest description
import hashlib
import json

from typing import Dict, List, Optional, Tuple
from osbuild.meta import Index, ValidationResult
from ..pipeline import Input, Manifest, Pipeline, detect_host_runner


def calc_id(name, build, base, options):
    m = hashlib.sha256()
    m.update(json.dumps(name, sort_keys=True).encode())
    m.update(json.dumps(build, sort_keys=True).encode())
    m.update(json.dumps(base, sort_keys=True).encode())
    m.update(json.dumps(options, sort_keys=True).encode())
    return m.hexdigest()

def describe(manifest: Manifest, *, with_id=False) -> Dict:
    """Create the manifest description for the pipeline"""

    # Can only describe what we loaded
    assert isinstance(manifest.loader, Loader), "Unexpected Loader"
    loader = manifest.loader

    ids = {v: k for k, v in loader.ids.items()}

    def describe_stage(stage):
        description = {"name": stage.name}
        if stage.options:
            description["options"] = stage.options
        if with_id:
            description["id"] = ids.get(stage.id, stage.id)
        return description

    def describe_pipeline(pipeline: Pipeline) -> Dict:
        description = {}
        if pipeline.build:
            build = manifest[pipeline.build]
            description["build"] = {
                "pipeline": describe_pipeline(build),
                "runner": pipeline.runner
            }

        if pipeline.stages:
            stages = [describe_stage(s) for s in pipeline.stages]
            description["stages"] = stages

        return description

    pipeline = describe_pipeline(loader.pipeline)

    if loader.assembler:
        assembler = describe_stage(loader.assembler.stages[0])
        pipeline["assembler"] = assembler

    description = {
        "pipeline": pipeline
    }

    if manifest.source_options:
        description["sources"] = manifest.source_options

    return description


class Loader:
    def __init__(self, index: Index, sources_options: Dict):
        self.index = index
        self.sources_options = sources_options

        # state
        self.pipelines: List[Pipeline] = []

        # mapping
        self.ids = {}
        self.pipeline = None # The main pipeline
        self.assembler = None # The old assembler

    def add_assembler(self, desc: Dict):
        if not desc:
            return

        build = self.pipeline.build
        base = self.pipeline.tree_id

        name = desc["name"]
        options = desc.get("options", {})

        pipeline = Pipeline(self.pipeline.runner, self.pipeline.build)
        pipeline.export = True
        self.pipelines.append(pipeline)

        info = self.index.get_module_info("Assembler", name)

        stage = pipeline.add_stage(info, self.sources_options, options)
        stage.inputs = [Input("tree", "pipeline", {"id": base})]

        new_id = stage.id
        old_id = calc_id(name, build, base, options)

        self.ids[old_id] = new_id
        self.assembler = pipeline

    def load_build(self, description: Dict):
        pipeline = description.get("pipeline")
        if pipeline:
            build_pipeline = self.load_pipeline(pipeline)
        else:
            build_pipeline = None

        return build_pipeline, description["runner"]

    def load_pipeline(self, description: Dict) -> Pipeline:
        build = description.get("build")
        if build:
            build_pipeline, runner = self.load_build(build)
        else:
            build_pipeline, runner = None, detect_host_runner()

        build_id = build_pipeline and build_pipeline.tree_id
        pipeline = Pipeline(runner, build_id)

        for s in description.get("stages", []):
            info = self.index.get_module_info("Stage", s["name"])
            pipeline.add_stage(info, self.sources_options, s.get("options", {}))

        self.pipelines.append(pipeline)

        return pipeline

    def load(self, description: Dict) -> Manifest:
        self.pipelines = []
        self.pipeline = self.load_pipeline(description)

        self.add_assembler(description.get("assembler"))

        manifest = Manifest(self.pipelines)
        manifest.source_options = self.sources_options
        manifest.loader = self

        return manifest


def load(description: Dict, index: Index) -> Manifest:
    """Load a manifest description"""

    pipeline = description.get("pipeline", {})
    sources = description.get("sources", {})

    loader = Loader(index, sources)
    manifest = loader.load(pipeline)

    return manifest


def map_ids(manifest: Manifest, ids: List[str]) -> List[str]:
    assert isinstance(manifest.loader, Loader), "Unexpected Loader"
    return [manifest.loader.ids.get(i, i) for i in ids]

def get_ids(manifest: Manifest) -> Tuple[Optional[str], Optional[str]]:
    # Can only get ids for what we loaded
    assert isinstance(manifest.loader, Loader), "Unexpected Loader"
    loader = manifest.loader
    pipeline = loader.pipeline
    assembler = loader.assembler

    return pipeline.tree_id, assembler and assembler.tree_id


def output(manifest: Manifest, res: Dict) -> Dict:
    """Convert a result into the v1 format"""

    def result_for_pipeline(pipeline):
        current = res[pipeline.id]
        retval = {"success": current["success"]}
        if pipeline.build:
            build = manifest[pipeline.build]
            retval["build"] = result_for_pipeline(build)
        stages = current.get("stages")
        if stages:
            retval["stages"] = stages
        assembler = current.get("assembler")
        if assembler:
            retval["assembler"] = assembler
        return retval

    assert isinstance(manifest.loader, Loader), "Unexpected Loader"

    result = result_for_pipeline(manifest.loader.pipeline)

    if manifest.loader.assembler:
        current = res[manifest.loader.assembler.id]
        result["assembler"] = current["stages"][0]

    return result


def validate(manifest: Dict, index: Index) -> ValidationResult:
    """Validate a OSBuild manifest

    This function will validate a OSBuild manifest, including
    all its stages and assembler and build manifests. It will
    try to validate as much as possible and not stop on errors.
    The result is a `ValidationResult` object that can be used
    to check the overall validation status and iterate all the
    individual validation errors.
    """

    schema = index.get_schema("Manifest")
    result = schema.validate(manifest)

    # main pipeline
    pipeline = manifest.get("pipeline", {})

    # recursively validate the build pipeline  as a "normal"
    # pipeline in order to validate its stages and assembler
    # options; for this it is being re-parented in a new plain
    # {"pipeline": ...} dictionary. NB: Any nested structural
    # errors might be detected twice, but de-duplicated by the
    # `ValidationResult.merge` call
    build = pipeline.get("build", {}).get("pipeline")
    if build:
        res = validate({"pipeline": build}, index=index)
        result.merge(res, path=["pipeline", "build"])

    stages = pipeline.get("stages", [])
    for i, stage in enumerate(stages):
        name = stage["name"]
        schema = index.get_schema("Stage", name)
        res = schema.validate(stage)
        result.merge(res, path=["pipeline", "stages", i])

    asm = pipeline.get("assembler", {})
    if asm:
        name = asm["name"]
        schema = index.get_schema("Assembler", name)
        res = schema.validate(asm)
        result.merge(res, path=["pipeline", "assembler"])

    # sources
    sources = manifest.get("sources", {})
    for name, source in sources.items():
        schema = index.get_schema("Source", name)
        res = schema.validate(source)
        result.merge(res, path=["sources", name])

    return result
