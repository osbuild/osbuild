# Version 1 of the manifest description

from typing import Dict
from osbuild.meta import Index, ValidationResult
from ..pipeline import Pipeline, detect_host_runner


def load_build(description: Dict, sources_options: Dict):
    pipeline = description.get("pipeline")
    if pipeline:
        build_pipeline = load_pipeline(pipeline, sources_options)
    else:
        build_pipeline = None

    return build_pipeline, description["runner"]


def load_pipeline(description: Dict, sources_options: Dict) -> Pipeline:
    build = description.get("build")
    if build:
        build_pipeline, runner = load_build(build, sources_options)
    else:
        build_pipeline, runner = None, detect_host_runner()

    pipeline = Pipeline(runner, build_pipeline)

    for s in description.get("stages", []):
        pipeline.add_stage(s["name"], sources_options, s.get("options", {}))

    a = description.get("assembler")
    if a:
        pipeline.set_assembler(a["name"], a.get("options", {}))

    return pipeline


def load(description: Dict) -> Pipeline:
    """Load a manifest description"""

    pipeline = description.get("pipeline", {})
    sources = description.get("sources", {})

    return load_pipeline(pipeline, sources)


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
