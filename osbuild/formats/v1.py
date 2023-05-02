""" Version 1 of the manifest description

This is the first version of the osbuild manifest description,
that has a "main" pipeline that consists of zero or more stages
to create a tree and optionally one assembler that assembles
the created tree into an artefact. The pipeline can have any
number of nested build pipelines. A sources section is used
to fetch resources.
"""
from typing import Any, Dict

from osbuild.meta import Index, ValidationResult

from ..pipeline import BuildResult, Manifest, Pipeline, Runner

VERSION = "1"


def describe(manifest: Manifest, *, with_id=False) -> Dict[str, Any]:
    """Create the manifest description for the pipeline"""
    def describe_stage(stage) -> Dict[str, Any]:
        description = {"name": stage.name}
        if stage.options:
            description["options"] = stage.options
        if with_id:
            description["id"] = stage.id
        return description

    def describe_pipeline(pipeline: Pipeline) -> Dict[str, Any]:
        description: Dict[str, Any] = {}
        if pipeline.build:
            build = manifest[pipeline.build]
            description["build"] = {
                "pipeline": describe_pipeline(build),
                "runner": pipeline.runner.name
            }

        if pipeline.stages:
            stages = [describe_stage(s) for s in pipeline.stages]
            description["stages"] = stages

        return description

    def get_source_name(source):
        name = source.info.name
        if name == "org.osbuild.curl":
            name = "org.osbuild.files"
        return name

    pipeline = describe_pipeline(manifest["tree"])

    assembler = manifest.get("assembler")
    if assembler:
        description = describe_stage(assembler.stages[0])
        pipeline["assembler"] = description

    description = {"pipeline": pipeline}

    if manifest.sources:
        sources = {
            get_source_name(s): s.options
            for s in manifest.sources
        }
        description["sources"] = sources

    return description


def load_assembler(description: Dict, index: Index, manifest: Manifest):
    pipeline = manifest["tree"]

    build, base, runner = pipeline.build, pipeline.id, pipeline.runner
    name, options = description["name"], description.get("options", {})

    # Add a pipeline with one stage for our assembler
    pipeline = manifest.add_pipeline("assembler", runner, build)

    info = index.get_module_info("Assembler", name)

    stage = pipeline.add_stage(info, options, {})
    info = index.get_module_info("Input", "org.osbuild.tree")
    ip = stage.add_input("tree", info, "org.osbuild.pipeline")
    ip.add_reference(base)
    return pipeline


def load_build(description: Dict, index: Index, manifest: Manifest, n: int):
    pipeline = description.get("pipeline")
    if pipeline:
        build_pipeline = load_pipeline(pipeline, index, manifest, n + 1)
    else:
        build_pipeline = None

    runner_name = description["runner"]
    runner_info = index.detect_runner(runner_name)

    return build_pipeline, Runner(runner_info, runner_name)


def load_stage(description: Dict, index: Index, pipeline: Pipeline):
    name = description["name"]
    opts = description.get("options", {})
    info = index.get_module_info("Stage", name)

    stage = pipeline.add_stage(info, opts)

    if stage.name == "org.osbuild.rpm":
        info = index.get_module_info("Input", "org.osbuild.files")
        ip = stage.add_input("packages", info, "org.osbuild.source")
        for pkg in stage.options["packages"]:
            options = None
            if isinstance(pkg, dict):
                gpg = pkg.get("check_gpg")
                if gpg:
                    options = {"metadata": {"rpm.check_gpg": gpg}}
                pkg = pkg["checksum"]
            ip.add_reference(pkg, options)
    elif stage.name == "org.osbuild.ostree":
        info = index.get_module_info("Input", "org.osbuild.ostree")
        ip = stage.add_input("commits", info, "org.osbuild.source")
        commit, ref = opts["commit"], opts.get("ref")
        options = {"ref": ref} if ref else None
        ip.add_reference(commit, options)


def load_source(name: str, description: Dict, index: Index, manifest: Manifest):
    if name == "org.osbuild.files":
        name = "org.osbuild.curl"

    info = index.get_module_info("Source", name)

    if name == "org.osbuild.curl":
        items = description["urls"]
    elif name == "org.osbuild.ostree":
        items = description["commits"]
    elif name == "org.osbuild.librepo":
        items = description["items"]
    else:
        raise ValueError(f"Unknown source type: {name}")

    # NB: the entries, i.e. `urls`, `commits` are left in the
    # description dict, although the sources are not using
    # it anymore. The reason is that it makes `describe` work
    # without any special casing

    manifest.add_source(info, items, description)


def load_pipeline(description: Dict, index: Index, manifest: Manifest, n: int = 0) -> Pipeline:
    build = description.get("build")
    if build:
        build_pipeline, runner = load_build(build, index, manifest, n)
    else:
        build_pipeline, runner = None, Runner(index.detect_host_runner())

    # the "main" pipeline is called `tree`, since it is building the
    # tree that will later be used by the `assembler`. Nested build
    # pipelines will get call "build", and "build-build-...", where
    # the number of repetitions is equal their level of nesting
    if not n:
        name = "tree"
    else:
        name = "-".join(["build"] * n)

    build_id = build_pipeline and build_pipeline.id
    pipeline = manifest.add_pipeline(name, runner, build_id)

    for stage in description.get("stages", []):
        load_stage(stage, index, pipeline)

    return pipeline


def load(description: Dict, index: Index) -> Manifest:
    """Load a manifest description"""

    pipeline = description.get("pipeline", {})
    sources = description.get("sources", {})

    manifest = Manifest()

    load_pipeline(pipeline, index, manifest)

    # load the assembler, if any
    assembler = pipeline.get("assembler")
    if assembler:
        load_assembler(assembler, index, manifest)

    # load the sources
    for name, desc in sources.items():
        load_source(name, desc, index, manifest)

    for pipeline in manifest.pipelines.values():
        for stage in pipeline.stages:
            stage.sources = sources

    return manifest


def output(manifest: Manifest, res: Dict, store=None) -> Dict:
    """Convert a result into the v1 format"""

    def result_for_stage(result: BuildResult, obj):
        return {
            "id": result.id,
            "type": result.name,
            "success": result.success,
            "error": result.error,
            "output": result.output,
            "metadata": obj and obj.meta.get(result.id),
        }

    def result_for_pipeline(pipeline):
        # The pipeline might not have been built one of its
        # dependencies, i.e. its build pipeline, failed to
        # build. We thus need to be tolerant of a missing
        # result but still need to to recurse
        current = res.get(pipeline.id, {})
        retval = {
            "success": current.get("success", True)
        }

        if pipeline.build:
            build = manifest[pipeline.build]
            retval["build"] = result_for_pipeline(build)
            retval["success"] = retval["build"]["success"]

        obj = store and pipeline.id and store.get(pipeline.id)

        stages = current.get("stages")
        if stages:
            retval["stages"] = [
                result_for_stage(r, obj) for r in stages
            ]
        return retval

    result = result_for_pipeline(manifest["tree"])

    assembler = manifest.get("assembler")
    if not assembler:
        return result

    current = res.get(assembler.id)
    # if there was an error before getting to the assembler
    # pipeline, there might not be a result present
    if not current:
        return result

    # The assembler pipeline must have exactly one stage
    # which is the v1 assembler
    obj = store and store.get(assembler.id)
    stage = current["stages"][0]
    result["assembler"] = result_for_stage(stage, obj)
    if not result["assembler"]["success"]:
        result["success"] = False

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
        if name == "org.osbuild.files":
            name = "org.osbuild.curl"
        schema = index.get_schema("Source", name)
        res = schema.validate(source)
        result.merge(res, path=["sources", name])

    return result
