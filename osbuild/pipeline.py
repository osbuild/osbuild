import collections
import contextlib
import hashlib
import json
import os
from typing import Dict, Iterator, List, Optional

from .api import API
from . import buildroot
from . import host
from . import objectstore
from . import remoteloop
from .inputs import Input
from .sources import Source
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
    def __init__(self, info, source_options, build, base, options):
        self.info = info
        self.sources = source_options
        self.build = build
        self.base = base
        self.options = options
        self.checkpoint = False
        self.inputs = {}

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
        if self.inputs:
            data = {n: i.id for n, i in self.inputs.items()}
            m.update(json.dumps(data, sort_keys=True).encode())
        return m.hexdigest()

    def add_input(self, name, info, origin, options=None):
        ip = Input(name, info, origin, options or {})
        self.inputs[name] = ip
        return ip

    def run(self, tree, runner, build_tree, store, monitor, libdir):
        with contextlib.ExitStack() as cm:

            build_root = buildroot.BuildRoot(build_tree, runner, libdir, store.tmp)
            cm.enter_context(build_root)

            inputs_tmpdir = store.tempdir(prefix="inputs-")
            inputs_tmpdir = cm.enter_context(inputs_tmpdir)
            inputs_mapped = "/run/osbuild/inputs"
            inputs = {}

            args = {
                "tree": "/run/osbuild/tree",
                "options": self.options,
                "paths": {
                    "inputs": inputs_mapped
                },
                "inputs": inputs,
                "meta": {
                    "id": self.id
                }
            }

            ro_binds = [
                f"{self.info.path}:/run/osbuild/bin/{self.name}",
                f"{inputs_tmpdir}:{inputs_mapped}"
            ]

            storeapi = objectstore.StoreServer(store)
            cm.enter_context(storeapi)

            mgr = host.ServiceManager(monitor=monitor)
            cm.enter_context(mgr)

            for key, ip in self.inputs.items():
                data = ip.map(mgr, storeapi, inputs_tmpdir)
                inputs[key] = data

            api = API(args, monitor)
            build_root.register_api(api)

            rls = remoteloop.LoopServer()
            build_root.register_api(rls)

            r = build_root.run([f"/run/osbuild/bin/{self.name}"],
                               monitor,
                               binds=[os.fspath(tree) + ":/run/osbuild/tree"],
                               readonly_binds=ro_binds)

        return BuildResult(self, r.returncode, r.output, api.metadata, api.error)


class Pipeline:
    def __init__(self, name: str, runner=None, build=None):
        self.name = name
        self.build = build
        self.runner = runner
        self.stages = []
        self.assembler = None
        self.export = False

    @property
    def id(self):
        """
        Pipeline id: corresponds to the `id` of the last stage

        In contrast to `name` this identifies the pipeline via
        the tree, i.e. the content, it produces. Therefore two
        pipelines that produce the same `tree`, i.e. have the
        same exact stages and build pipeline, will have the
        same `id`; thus the `id`, in contrast to `name` does
        not uniquely identify a pipeline.
        In case a Pipeline has no stages, its `id` is `None`.
        """
        return self.stages[-1].id if self.stages else None

    def add_stage(self, info, options, sources_options=None):
        stage = Stage(info, sources_options, self.build, self.id, options or {})
        self.stages.append(stage)
        if self.assembler:
            self.assembler.base = stage.id
        return stage

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

        # Check if the tree that we are supposed to build does
        # already exist. If so, short-circuit here
        tree = object_store.get(self.id)

        if tree:
            return results, build_tree, tree

        # Not in the store yet, need to actually build it, but maybe
        # an intermediate checkpoint exists: Find the last stage that
        # already exists in the store and use that as the base.
        tree = object_store.new()
        base_idx = -1
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

            # The content of the tree now corresponds to the stage that
            # was build and this can can be identified via the id of it
            tree.id = stage.id

            if stage.checkpoint:
                object_store.commit(tree, stage.id)

        return results, build_tree, tree

    def run(self, store, monitor, libdir, output_directory):
        results = {"success": True}

        monitor.begin(self)

        # If the final result is already in the store, no need to attempt
        # building it. Just fetch the cached information. If the associated
        # tree exists, we return it as well, but we do not care if it is
        # missing, since it is not a mandatory part of the result and would
        # usually be needless overhead.
        obj = store.get(self.id)

        if not obj:
            results, _, obj = self.build_stages(store, monitor, libdir)

            if not results["success"]:
                return results

        if self.export and obj:
            if output_directory:
                obj.export(output_directory)

        monitor.finish(results)

        return results


class Manifest:
    """Representation of a pipeline and its sources"""

    def __init__(self):
        self.pipelines = collections.OrderedDict()
        self.sources: List[Source] = []

    def add_pipeline(self, name: str, runner: str, build: str) -> Pipeline:
        pipeline = Pipeline(name, runner, build)
        if name in self.pipelines:
            raise ValueError(f"Name {name} already exists")
        self.pipelines[name] = pipeline
        return pipeline

    def add_source(self, info, items: List, options: Dict) -> Source:
        source = Source(info, items, options)
        self.sources.append(source)
        return source

    def build(self, store, monitor, libdir, output_directory):
        results = {"success": True}

        for source in self.sources:
            source.download(store, libdir)

        for pl in self.pipelines.values():
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

        def mark_pipeline(pl):
            if pl.name in points and pl.stages:
                pl.stages[-1].checkpoint = True
                points.remove(pl.name)

            for stage in pl.stages:
                mark_stage(stage)

        for pl in self.pipelines.values():
            mark_pipeline(pl)

        return points

    def get(self, name_or_id: str) -> Optional[Pipeline]:
        pl = self.pipelines.get(name_or_id)
        if pl:
            return pl
        for pl in self.pipelines.values():
            if pl.id == name_or_id:
                return pl
        return None

    def __contains__(self, name_or_id: str) -> bool:
        return self.get(name_or_id) is not None

    def __getitem__(self, name_or_id: str) -> Pipeline:
        pl = self.get(name_or_id)
        if pl:
            return pl
        raise KeyError(f"'{name_or_id}' not found")

    def __iter__(self) -> Iterator[Pipeline]:
        return iter(self.pipelines.values())


def detect_host_runner():
    """Use os-release(5) to detect the runner for the host"""
    osname = osrelease.describe_os(*osrelease.DEFAULT_PATHS)
    return "org.osbuild." + osname
