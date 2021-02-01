# Version 1 of the manifest description

from typing import Dict, Optional, Tuple
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

        return description

    pipeline = describe_pipeline(manifest["tree"])

    assembler = manifest.get("assembler")
    if assembler:
        description = describe_stage(assembler.stages[0])
        pipeline["assembler"] = description

    description = {"pipeline": pipeline}

    if manifest.sources:
        sources = {
            s.info.name: s.options
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
    pipeline.export = True

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

    return build_pipeline, description["runner"]


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


def load_pipeline(description: Dict, index: Index, manifest: Manifest, n: int = 0) -> Pipeline:
    build = description.get("build")
    if build:
        build_pipeline, runner = load_build(build, index, manifest, n)
    else:
        build_pipeline, runner = None, detect_host_runner()

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
    for name, options in sources.items():
        info = index.get_module_info("Source", name)
        manifest.add_source(info, options)

    for pipeline in manifest.pipelines.values():
        for stage in pipeline.stages:
            stage.sources = sources

    return manifest


def get_ids(manifest: Manifest) -> Tuple[Optional[str], Optional[str]]:
    pipeline = manifest["tree"]
    assembler = manifest.get("assembler")
    return pipeline.id, assembler and assembler.id


def output(manifest: Manifest, res: Dict) -> Dict:
    """Convert a result into the v1 format"""

    def result_for_pipeline(pipeline):
        # The pipeline might not have been built one of its
        # dependencies, i.e. its build pipeline, failed to
        # build. We thus need to be tolerant of a missing
        # result but still need to to recurse
        current = res.get(pipeline.id, {})
        retval = {
            "success": current.get("success", False)
        }
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

    result = result_for_pipeline(manifest["tree"])

    assembler = manifest.get("assembler")
    if assembler:
        current = res.get(assembler.id)
        if current:
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
