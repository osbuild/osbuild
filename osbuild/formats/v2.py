""" Version 2 of the manifest description

Second, and current, version of the manifest description
"""
from typing import Dict
from osbuild.meta import Index, ModuleInfo, ValidationResult
from ..inputs import Input
from ..pipeline import Manifest, Pipeline, Stage, detect_host_runner
from ..sources import Source


VERSION = "2"


# pylint: disable=too-many-statements
def describe(manifest: Manifest, *, with_id=False) -> Dict:

    # Undo the build, runner pairing introduce by the loading
    # code. See the comment there for more details
    runners = {
        p.build: p.runner for p in manifest.pipelines.values()
        if p.build
    }

    def pipeline_ref(pid):
        if with_id:
            return pid

        pl = manifest[pid]
        return f"name:{pl.name}"

    def describe_device(dev):
        desc = {
            "type": dev.info.name
        }

        if dev.options:
            desc["options"] = dev.options

        return desc

    def describe_devices(devs: Dict):
        desc = {
            name: describe_device(dev)
            for name, dev in devs.items()
        }
        return desc

    def describe_input(ip: Input):
        origin = ip.origin
        desc = {
            "type": ip.info.name,
            "origin": origin,
        }
        if ip.options:
            desc["options"] = ip.options

        refs = {}
        for name, ref in ip.refs.items():
            if origin == "org.osbuild.pipeline":
                name = pipeline_ref(name)
            refs[name] = ref

        if refs:
            desc["references"] = refs

        return desc

    def describe_inputs(ips: Dict[str, Input]):
        desc = {
            name: describe_input(ip)
            for name, ip in ips.items()
        }
        return desc

    def describe_mount(mnt):
        desc = {
            "type": mnt.info.name,
            "device": mnt.device.name,
            "target": mnt.target
        }

        if mnt.options:
            desc["options"] = mnt.options
        return desc

    def describe_mounts(mounts: Dict):
        desc = {
            name: describe_mount(mnt)
            for name, mnt in mounts.items()
        }
        return desc

    def describe_stage(s: Stage):
        desc = {
            "type": s.info.name
        }

        if with_id:
            desc["id"] = s.id

        if s.options:
            desc["options"] = s.options

        devs = describe_devices(s.devices)
        if devs:
            desc["devices"] = devs

        mounts = describe_mounts(s.mounts)
        if mounts:
            desc["mounts"] = mounts

        ips = describe_inputs(s.inputs)
        if ips:
            desc["inputs"] = ips

        return desc

    def describe_pipeline(p: Pipeline):
        desc = {
            "name": p.name
        }

        if p.build:
            desc["build"] = pipeline_ref(p.build)

        runner = runners.get(p.id)
        if runner:
            desc["runner"] = runner

        stages = [
            describe_stage(stage)
            for stage in p.stages
        ]

        if stages:
            desc["stages"] = stages

        return desc

    def describe_source(s: Source):
        desc = {
            "items": s.items
        }

        return desc

    pipelines = [
        describe_pipeline(pipeline)
        for pipeline in manifest.pipelines.values()
    ]

    sources = {
        source.info.name: describe_source(source)
        for source in manifest.sources
    }

    description = {
        "version": VERSION,
        "pipelines": pipelines
    }

    if sources:
        description["sources"] = sources

    return description


def resolve_ref(name: str, manifest: Manifest) -> str:
    ref = name[5:]
    target = manifest.pipelines.get(ref)
    if not target:
        raise ValueError(f"Unknown pipeline reference: name:{ref}")
    return target.id


def load_device(name: str, description: Dict, index: Index, stage: Stage):
    device_type = description["type"]
    options = description.get("options", {})

    info = index.get_module_info("Device", device_type)
    if not info:
        raise TypeError(f"Missing meta information for {device_type}")
    stage.add_device(name, info, options)


def load_input(name: str, description: Dict, index: Index, stage: Stage, manifest: Manifest):
    input_type = description["type"]
    origin = description["origin"]
    options = description.get("options", {})

    info = index.get_module_info("Input", input_type)
    ip = stage.add_input(name, info, origin, options)

    refs = description.get("references", {})

    if isinstance(refs, list):
        refs = {r: {} for r in refs}

    if origin == "org.osbuild.pipeline":
        resolved = {}
        for r, desc in refs.items():
            if not r.startswith("name:"):
                continue
            target = resolve_ref(r, manifest)
            resolved[target] = desc
        refs = resolved

    for r, desc in refs.items():
        ip.add_reference(r, desc)


def load_mount(name: str, description: Dict, index: Index, stage: Stage):
    mount_type = description["type"]
    info = index.get_module_info("Mount", mount_type)

    source = description["source"]
    target = description["target"]

    options = description.get("options", {})

    device = stage.devices.get(source)
    if not device:
        raise ValueError(f"Unknown device '{source}' for mount '{name}'")

    stage.add_mount(name, info, device, target, options)


def load_stage(description: Dict, index: Index, pipeline: Pipeline, manifest: Manifest):
    stage_type = description["type"]
    opts = description.get("options", {})
    info = index.get_module_info("Stage", stage_type)

    stage = pipeline.add_stage(info, opts)

    devs = description.get("devices", {})
    for name, desc in devs.items():
        load_device(name, desc, index, stage)

    ips = description.get("inputs", {})
    for name, desc in ips.items():
        load_input(name, desc, index, stage, manifest)

    mounts = description.get("mounts", {})
    for name, desc in mounts.items():
        load_mount(name, desc, index, stage)

    return stage


def load_pipeline(description: Dict, index: Index, manifest: Manifest):
    name = description["name"]
    build = description.get("build")
    runner = description.get("runner")

    if build and build.startswith("name:"):
        target = resolve_ref(build, manifest)
        build = target

    pl = manifest.add_pipeline(name, runner, build)

    for desc in description.get("stages", []):
        load_stage(desc, index, pl, manifest)


def load(description: Dict, index: Index) -> Manifest:
    """Load a manifest description"""

    sources = description.get("sources", {})
    pipelines = description.get("pipelines", [])

    manifest = Manifest()

    # load the sources
    for name, desc in sources.items():
        info = index.get_module_info("Source", name)
        items = desc.get("items", {})
        options = desc.get("options", {})
        manifest.add_source(info, items, options)

    for desc in pipelines:
        load_pipeline(desc, index, manifest)

    # The "runner" property in the manifest format is the
    # runner to the run the pipeline with. In osbuild the
    # "runner" property belongs to the "build" pipeline,
    # i.e. is what runner to use for it. This we have to
    # go through the pipelines and fix things up
    pipelines = manifest.pipelines.values()

    host_runner = detect_host_runner()
    runners = {
        pl.id: pl.runner for pl in pipelines
    }

    for pipeline in pipelines:
        if not pipeline.build:
            pipeline.runner = host_runner
            continue

        runner = runners[pipeline.build]
        pipeline.runner = runner

    return manifest


#pylint: disable=too-many-branches
def output(manifest: Manifest, res: Dict) -> Dict:
    """Convert a result into the v2 format"""

    if not res["success"]:
        last = list(res.keys())[-1]
        failed = res[last]["stages"][-1]

        result = {
            "type": "error",
            "success": False,
            "error": {
                "type": "org.osbuild.error.stage",
                "details": {
                    "stage": {
                        "id": failed["id"],
                        "type": failed["name"],
                        "output": failed["output"],
                        "error": failed["error"]
                    }
                }
            }
        }
    else:
        result = {
            "type": "result",
            "success": True,
            "metadata": {}
        }

        # gather all the metadata
        for p in manifest.pipelines.values():
            data = {}
            r = res[p.id]
            for stage in r.get("stages", []):
                md = stage.get("metadata")
                if not md:
                    continue
                name = stage["name"]
                val = data.setdefault(name, {})
                val.update(md)

            if data:
                result["metadata"][p.name] = data

    # generate the log
    result["log"] = {}
    for p in manifest.pipelines.values():
        r = res.get(p.id, {})
        log = []

        for stage in r.get("stages", []):
            data = {
                "id": stage["id"],
                "type": stage["name"],
                "output": stage["output"]
            }
            if not stage["success"]:
                data["success"] = stage["success"]
                if stage["error"]:
                    data["error"] = stage["error"]

            log.append(data)

        if log:
            result["log"][p.name] = log

    return result


def validate(manifest: Dict, index: Index) -> ValidationResult:

    schema = index.get_schema("Manifest", version="2")
    result = schema.validate(manifest)

    def validate_module(mod, klass, path):
        name = mod["type"]
        schema = index.get_schema(klass, name, version="2")
        res = schema.validate(mod)
        result.merge(res, path=path)

    def validate_stage_modules(klass, stage, path):
        group = ModuleInfo.MODULES[klass]
        items = stage.get(group, {})
        for name, mod in items.items():
            validate_module(mod, klass, path + [group, name])

    def validate_stage(stage, path):
        name = stage["type"]
        schema = index.get_schema("Stage", name, version="2")
        res = schema.validate(stage)
        result.merge(res, path=path)

        for mod in ("Device", "Input", "Mount"):
            validate_stage_modules(mod, stage, path)

    def validate_pipeline(pipeline, path):
        stages = pipeline.get("stages", [])
        for i, stage in enumerate(stages):
            validate_stage(stage, path + ["stages", i])

    # sources
    sources = manifest.get("sources", {})
    for name, source in sources.items():
        schema = index.get_schema("Source", name, version="2")
        res = schema.validate(source)
        result.merge(res, path=["sources", name])

    # pipelines
    pipelines = manifest.get("pipelines", [])
    for i, pipeline in enumerate(pipelines):
        validate_pipeline(pipeline, path=["pipelines", i])

    return result
