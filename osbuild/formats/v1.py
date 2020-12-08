# Version 1 of the manifest description

from ..pipeline import Pipeline, detect_host_runner


def load_build(description, sources_options):
    pipeline = description.get("pipeline")
    if pipeline:
        build_pipeline = load(pipeline, sources_options)
    else:
        build_pipeline = None

    return build_pipeline, description["runner"]


def load(description, sources_options):
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
