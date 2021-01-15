# Version 1 of the manifest description

from typing import Dict, List, Optional, Tuple
from osbuild.meta import Index, ValidationResult
from ..pipeline import Manifest, Pipeline, detect_host_runner


def describe(manifest: Manifest, *, with_id=False) -> Dict:
    """Create the manifest description for the pipeline"""
    def describe_stage(stage):
        description = {"name": stage.name}
        if stage.options:
            description["options"] = stage.options
        if with_id:
            description["id"] = stage.id
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

        if pipeline.assembler:
            assembler = describe_stage(pipeline.assembler)
            description["assembler"] = assembler
        return description

    description = {
        "pipeline": describe_pipeline(manifest.pipelines[-1])
    }

    if manifest.sources:
        description["sources"] = manifest.sources

    return description


def load_build(description: Dict, sources_options: Dict, result: List[Pipeline]):
    pipeline = description.get("pipeline")
    if pipeline:
        build_pipeline = load_pipeline(pipeline, sources_options, result)
    else:
        build_pipeline = None

    return build_pipeline, description["runner"]


def load_pipeline(description: Dict, sources_options: Dict, result: List[Pipeline]) -> Pipeline:
    build = description.get("build")
    if build:
        build_pipeline, runner = load_build(build, sources_options, result)
    else:
        build_pipeline, runner = None, detect_host_runner()


    pipeline = Pipeline(runner, build_pipeline and build_pipeline.tree_id)

    for s in description.get("stages", []):
        pipeline.add_stage(s["name"], s.get("options", {}), sources_options)

    a = description.get("assembler")
    if a:
        pipeline.set_assembler(a["name"], a.get("options", {}))

    result.append(pipeline)

    return pipeline


def load(description: Dict) -> Manifest:
    """Load a manifest description"""

    pipeline = description.get("pipeline", {})
    sources = description.get("sources", {})

    pipelines = []

    load_pipeline(pipeline, sources, pipelines)

    manifest = Manifest(pipelines, sources)

    return manifest


def get_ids(manifest: Manifest) -> Tuple[Optional[str], Optional[str]]:
    pipeline = manifest.pipelines[-1]
    return pipeline.tree_id, pipeline.output_id


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

    return result_for_pipeline(manifest.pipelines[-1])


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
