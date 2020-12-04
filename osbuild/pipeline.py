
import hashlib
import json
import os
import tempfile

from .api import API
from . import buildroot
from . import objectstore
from . import remoteloop
from . import sources
from .util import osrelease


def cleanup(*objs):
    """Call cleanup method for all objects, filters None values out"""
    _ = map(lambda o: o.cleanup(), filter(None, objs))


class BuildResult:
    def __init__(self, origin, returncode, output, metadata, error):
        self.name = origin.name
        self.id = origin.id
        self.options = origin.options
        self.success = returncode == 0
        self.output = output
        self.metadata = metadata
        self.error = error

    def as_dict(self):
        return vars(self)


class Stage:
    def __init__(self, name, source_options, build, base, options):
        self.name = name
        self.sources = source_options
        self.build = build
        self.base = base
        self.options = options
        self.checkpoint = False

    @property
    def id(self):
        m = hashlib.sha256()
        m.update(json.dumps(self.name, sort_keys=True).encode())
        m.update(json.dumps(self.build, sort_keys=True).encode())
        m.update(json.dumps(self.base, sort_keys=True).encode())
        m.update(json.dumps(self.options, sort_keys=True).encode())
        return m.hexdigest()

    def description(self, *, with_id=False):
        description = {"name": self.name}
        if self.options:
            description["options"] = self.options
        if with_id:
            description["id"] = self.id
        return description

    def run(self,
            tree,
            runner,
            build_tree,
            cache,
            monitor,
            libdir,
            var="/var/tmp"):
        with buildroot.BuildRoot(build_tree, runner, libdir, var=var) as build_root, \
            tempfile.TemporaryDirectory(prefix="osbuild-sources-output-", dir=var) as sources_output:

            args = {
                "tree": "/run/osbuild/tree",
                "sources": "/run/osbuild/sources",
                "options": self.options,
                "meta": {
                    "id": self.id
                }
            }

            ro_binds = [f"{sources_output}:/run/osbuild/sources"]

            api = API(args, monitor)
            build_root.register_api(api)

            src = sources.SourcesServer(libdir,
                                        self.sources,
                                        os.path.join(cache, "sources"),
                                        sources_output)
            build_root.register_api(src)

            r = build_root.run([f"/run/osbuild/lib/stages/{self.name}"],
                               monitor,
                               binds=[os.fspath(tree) + ":/run/osbuild/tree"],
                               readonly_binds=ro_binds)

        return BuildResult(self, r.returncode, r.output, api.metadata, api.error)


class Assembler:
    def __init__(self, name, build, base, options):
        self.name = name
        self.build = build
        self.base = base
        self.options = options
        self.checkpoint = False

    @property
    def id(self):
        m = hashlib.sha256()
        m.update(json.dumps(self.name, sort_keys=True).encode())
        m.update(json.dumps(self.build, sort_keys=True).encode())
        m.update(json.dumps(self.base, sort_keys=True).encode())
        m.update(json.dumps(self.options, sort_keys=True).encode())
        return m.hexdigest()

    def description(self, *, with_id=False):
        description = {"name": self.name}
        if self.options:
            description["options"] = self.options
        if with_id:
            description["id"] = self.id
        return description

    def run(self, tree, runner, build_tree, monitor, libdir, output_dir, var="/var/tmp"):
        with buildroot.BuildRoot(build_tree, runner, libdir, var=var) as build_root:

            args = {
                "tree": "/run/osbuild/tree",
                "options": self.options,
                "meta": {
                    "id": self.id
                }
            }

            binds = []

            output_dir = os.fspath(output_dir)
            os.makedirs(output_dir, exist_ok=True)
            binds.append(f"{output_dir}:/run/osbuild/output")
            args["output_dir"] = "/run/osbuild/output"

            ro_binds = [os.fspath(tree) + ":/run/osbuild/tree"]

            api = API(args, monitor)
            build_root.register_api(api)

            rls = remoteloop.LoopServer()
            build_root.register_api(rls)

            r = build_root.run([f"/run/osbuild/lib/assemblers/{self.name}"],
                               monitor,
                               binds=binds,
                               readonly_binds=ro_binds)

        return BuildResult(self, r.returncode, r.output, api.metadata, api.error)


class Pipeline:
    def __init__(self, runner=None, build=None):
        self.build = build
        self.runner = runner
        self.stages = []
        self.assembler = None

    @property
    def tree_id(self):
        return self.stages[-1].id if self.stages else None

    @property
    def output_id(self):
        return self.assembler.id if self.assembler else None

    def add_stage(self, name, sources_options=None, options=None):
        build = self.build.tree_id if self.build else None
        stage = Stage(name, sources_options, build, self.tree_id, options or {})
        self.stages.append(stage)
        if self.assembler:
            self.assembler.base = stage.id

    def set_assembler(self, name, options=None):
        build = self.build.tree_id if self.build else None
        self.assembler = Assembler(name, build, self.tree_id, options or {})

    def description(self, *, with_id=False):
        description = {}
        if self.build:
            description["build"] = {
                "pipeline": self.build.description(with_id=with_id),
                "runner": self.runner
            }
        if self.stages:
            stages = [s.description(with_id=with_id) for s in self.stages]
            description["stages"] = stages
        if self.assembler:
            assembler = self.assembler.description(with_id=with_id)
            description["assembler"] = assembler

        return description

    def build_stages(self, object_store, monitor, libdir):
        results = {"success": True}

        # We need a build tree for the stages below, which is either
        # another tree that needs to be built with the build pipeline
        # or the host file system if no build pipeline is specified
        # NB: the very last level of nested build pipelines is always
        # build on the host

        if not self.build:
            build_tree = objectstore.HostTree(object_store)
        else:
            build = self.build

            r, t, tree = build.build_stages(object_store,
                                            monitor,
                                            libdir)

            results["build"] = r
            if not r["success"]:
                results["success"] = False
                return results, None, None

            # Cleanup the build tree (`t`) which was used to
            # build `tree`; it is now not needed anymore
            t.cleanup()

            build_tree = tree

        # If there are no stages, just return build tree we just
        # obtained and a new, clean `tree`
        if not self.stages:
            tree = object_store.new()
            return results, build_tree, tree

        # Create a new tree. The base is our tree_id because if that
        # is already in the store, we can short-circuit directly and
        # exit directly; `tree` is then used to read the tree behind
        # `self.tree_id`
        tree = object_store.new(base_id=self.tree_id)

        if object_store.contains(self.tree_id):
            return results, build_tree, tree

        # Not in the store yet, need to actually build it, but maybe
        # an intermediate checkpoint exists: Find the last stage that
        # already exists in the store and use that as the base.
        base_idx = -1
        tree.base = None
        for i in reversed(range(len(self.stages))):
            if object_store.contains(self.stages[i].id):
                tree.base = self.stages[i].id
                base_idx = i
                break

        # If two run() calls race each-other, two trees will get built
        # and it is nondeterministic which of them will end up
        # referenced by the `tree_id` in the content store if they are
        # both committed. However, after the call to commit all the
        # trees will be based on the winner.
        results["stages"] = []

        for stage in self.stages[base_idx + 1:]:
            with build_tree.read() as build_path, tree.write() as path:

                monitor.stage(stage)

                r = stage.run(path,
                              self.runner,
                              build_path,
                              object_store.store,
                              monitor,
                              libdir,
                              var=object_store.store)

                monitor.result(r)

            results["stages"].append(r.as_dict())
            if not r.success:
                cleanup(build_tree, tree)
                results["success"] = False
                return results, None, None

            if stage.checkpoint:
                object_store.commit(tree, stage.id)

        return results, build_tree, tree

    def assemble(self, object_store, build_tree, tree, monitor, libdir):
        results = {"success": True}

        if not self.assembler:
            return results, None

        output = object_store.new()

        with build_tree.read() as build_dir, \
             tree.read() as input_dir, \
             output.write() as output_dir:

            monitor.assembler(self.assembler)

            r = self.assembler.run(input_dir,
                                   self.runner,
                                   build_dir,
                                   monitor,
                                   libdir,
                                   output_dir,
                                   var=object_store.store)

            monitor.result(r)

        results["assembler"] = r.as_dict()
        if not r.success:
            output.cleanup()
            results["success"] = False
            return results, None

        if self.assembler.checkpoint:
            object_store.commit(output, self.assembler.id)

        return results, output

    def run(self, store, monitor, libdir, output_directory):
        results = {"success": True}

        monitor.begin(self)

        with objectstore.ObjectStore(store) as object_store:
            # If the final result is already in the store, no need to attempt
            # building it. Just fetch the cached information. If the associated
            # tree exists, we return it as well, but we do not care if it is
            # missing, since it is not a mandatory part of the result and would
            # usually be needless overhead.
            obj = object_store.get(self.output_id)

            if not obj:
                results, build_tree, tree = self.build_stages(object_store,
                                                              monitor,
                                                              libdir)

                if not results["success"]:
                    return results

                r, obj = self.assemble(object_store,
                                       build_tree,
                                       tree,
                                       monitor,
                                       libdir)

                results.update(r)  # This will also update 'success'

            if obj:
                if output_directory:
                    obj.export(output_directory)
                obj.cleanup()

        monitor.finish(results)

        return results


def detect_host_runner():
    """Use os-release(5) to detect the runner for the host"""
    osname = osrelease.describe_os(*osrelease.DEFAULT_PATHS)
    return "org.osbuild." + osname


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
