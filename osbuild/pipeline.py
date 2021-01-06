
import contextlib
import hashlib
import json
import os
import tempfile
from typing import List

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


class Input:
    def __init__(self, name, input_type, options):
        self.name = name
        self.type = input_type
        self.options = options


class Stage:
    def __init__(self, info, source_options, build, base, options):
        self.info = info
        self.sources = source_options
        self.build = build
        self.base = base
        self.options = options
        self.checkpoint = False
        self.inputs = []

    @property
    def name(self):
        return self.info.name

    @property
    def id(self):
        m = hashlib.sha256()
        m.update(json.dumps(self.name, sort_keys=True).encode())
        m.update(json.dumps(self.build, sort_keys=True).encode())
        m.update(json.dumps(self.base, sort_keys=True).encode())
        m.update(json.dumps(self.options, sort_keys=True).encode())
        return m.hexdigest()

    def run(self, tree, runner, build_tree, store, monitor, libdir):
        with contextlib.ExitStack() as cm:
            var = store.store

            build_root = buildroot.BuildRoot(build_tree, runner, libdir, var)
            cm.enter_context(build_root)

            sources_tmp = tempfile.TemporaryDirectory(prefix="osbuild-sources-output-", dir=var)
            sources_output = cm.enter_context(sources_tmp)

            args = {
                "tree": "/run/osbuild/tree",
                "sources": "/run/osbuild/sources",
                "options": self.options,
                "meta": {
                    "id": self.id
                }
            }

            ro_binds = [
                f"{self.info.path}:/run/osbuild/bin/{self.name}",
                f"{sources_output}:/run/osbuild/sources"
            ]

            inputs = {}
            for ip in self.inputs:
                assert ip.type == "pipeline"
                pid = ip.options["id"]
                if not pid:
                    obj = store.new()
                else:
                    obj = store.get(pid)
                path = cm.enter_context(obj.read())

                mapped = f"/run/osbuild/inputs/{ip.name}"
                inputs[ip.name] = {
                    "type": ip.type,
                    "path": mapped,
                    "meta": {
                        "options": ip.options
                    }
                }

                ro_binds += [
                    f"{path}:{mapped}"
                ]

            args["inputs"] = inputs

            api = API(args, monitor)
            build_root.register_api(api)

            src = sources.SourcesServer(libdir,
                                        self.sources,
                                        os.path.join(store.store, "sources"),
                                        sources_output)
            build_root.register_api(src)

            rls = remoteloop.LoopServer()
            build_root.register_api(rls)

            r = build_root.run([f"/run/osbuild/bin/{self.name}"],
                               monitor,
                               binds=[os.fspath(tree) + ":/run/osbuild/tree"],
                               readonly_binds=ro_binds)

        return BuildResult(self, r.returncode, r.output, api.metadata, api.error)


class Pipeline:
    def __init__(self, runner=None, build=None):
        self.build = build
        self.runner = runner
        self.stages = []
        self.assembler = None
        self.export = False

    @property
    def id(self):
        return self.tree_id or self.output_id

    @property
    def tree_id(self):
        return self.stages[-1].id if self.stages else None

    @property
    def output_id(self):
        return self.assembler.id if self.assembler else None

    def add_stage(self, info, sources_options=None, options=None):
        stage = Stage(info, sources_options, self.build, self.tree_id, options or {})
        self.stages.append(stage)
        if self.assembler:
            self.assembler.base = stage.id
        return stage

    def set_assembler(self, info, options=None):
        self.assembler = Stage(info, {}, self.build, self.tree_id, options or {})
        self.assembler.inputs = [Input("tree", "pipeline", {"id": self.tree_id})]

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
            build_tree = object_store.get(self.build)

        if not build_tree:
            raise AssertionError(f"build tree {self.build} not found")

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
                              object_store,
                              monitor,
                              libdir)

                monitor.result(r)

            results["stages"].append(r.as_dict())
            if not r.success:
                cleanup(build_tree, tree)
                results["success"] = False
                return results, None, None

            if stage.checkpoint:
                object_store.commit(tree, stage.id)

        # The for loop will always have done at least iteration since
        # both other cases, i.e. an empty list of stages or the last
        # stage being in the store, are handled before
        tree.id = stage.id  # pylint: disable=undefined-loop-variable

        return results, build_tree, tree

    def assemble(self, object_store, build_tree, monitor, libdir):
        results = {"success": True}

        if not self.assembler:
            return results, None

        output = object_store.new()

        with build_tree.read() as build_dir, \
             output.write() as output_dir:

            monitor.assembler(self.assembler)

            r = self.assembler.run(output_dir,
                                   self.runner,
                                   build_dir,
                                   object_store,
                                   monitor,
                                   libdir)

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

        # If the final result is already in the store, no need to attempt
        # building it. Just fetch the cached information. If the associated
        # tree exists, we return it as well, but we do not care if it is
        # missing, since it is not a mandatory part of the result and would
        # usually be needless overhead.
        obj = store.get(self.output_id)

        if not obj:
            results, build_tree, _ = self.build_stages(store,
                                                       monitor,
                                                       libdir)

            if not results["success"]:
                return results

            r, obj = self.assemble(store,
                                   build_tree,
                                   monitor,
                                   libdir)

            results.update(r)  # This will also update 'success'

        if self.export and obj:
            if output_directory:
                obj.export(output_directory)

        monitor.finish(results)

        return results


class Manifest:
    """A Pipeline with its source options"""

    def __init__(self, pipelines: List[Pipeline]):
        self.pipelines = pipelines
        self.source_options = {}
        self.loader = None

    def build(self, store, monitor, libdir, output_directory):
        results = {"success": True}

        for pl in self.pipelines:
            res = pl.run(store, monitor, libdir, output_directory)
            results[pl.id] = res
            if not res["success"]:
                results["success"] = False
                return results

        return results

    def mark_checkpoints(self, checkpoints):
        points = set(checkpoints)

        def mark_stage(stage):
            c = stage.id
            if c in points:
                stage.checkpoint = True
                points.remove(c)

        def mark_assembler(assembler):
            c = assembler.id
            if c in points:
                assembler.checkpoint = True
                points.remove(c)

        def mark_pipeline(pl):
            for stage in pl.stages:
                mark_stage(stage)
            if pl.assembler:
                mark_assembler(pl.assembler)

        for pl in self.pipelines:
            mark_pipeline(pl)

        return points

    def __getitem__(self, pipeline_id):
        for pl in self.pipelines:
            if pl.id == pipeline_id:
                return pl
        raise KeyError("{pipeline_id} not found")


def detect_host_runner():
    """Use os-release(5) to detect the runner for the host"""
    osname = osrelease.describe_os(*osrelease.DEFAULT_PATHS)
    return "org.osbuild." + osname
