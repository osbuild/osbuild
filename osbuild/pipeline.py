import collections
import contextlib
import hashlib
import json
import os
from typing import Dict, Generator, Iterable, Iterator, List, Optional

from .api import API
from . import buildroot
from . import host
from . import objectstore
from . import remoteloop
from .devices import Device, DeviceManager
from .inputs import Input, InputManager
from .mounts import Mount, MountManager
from .sources import Source
from .util import osrelease
from .objectstore import ObjectStore


DEFAULT_CAPABILITIES = {
    "CAP_AUDIT_WRITE",
    "CAP_CHOWN",
    "CAP_DAC_OVERRIDE",
    "CAP_DAC_READ_SEARCH",
    "CAP_FOWNER",
    "CAP_FSETID",
    "CAP_IPC_LOCK",
    "CAP_LINUX_IMMUTABLE",
    "CAP_MAC_OVERRIDE",
    "CAP_MKNOD",
    "CAP_NET_BIND_SERVICE",
    "CAP_SETFCAP",
    "CAP_SETGID",
    "CAP_SETPCAP",
    "CAP_SETUID",
    "CAP_SYS_ADMIN",
    "CAP_SYS_CHROOT",
    "CAP_SYS_NICE",
    "CAP_SYS_RESOURCE"
}


def cleanup(*objs):
    """Call cleanup method for all objects, filters None values out"""
    _ = map(lambda o: o.cleanup(), filter(None, objs))


class BuildResult:
    def __init__(self, origin, returncode, output, metadata, error):
        self.name = origin.name
        self.id = origin.id
        self.success = returncode == 0
        self.output = output
        self.metadata = metadata
        self.error = error

    def as_dict(self):
        return vars(self)


class Stage:
    def __init__(self, info, source_options, build, base, options, source_epoch):
        self.info = info
        self.sources = source_options
        self.build = build
        self.base = base
        self.options = options
        self.source_epoch = source_epoch
        self.checkpoint = False
        self.inputs = {}
        self.devices = {}
        self.mounts = {}

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
        if self.source_epoch is not None:
            m.update(json.dumps(self.source_epoch, sort_keys=True).encode())
        if self.inputs:
            data = {n: i.id for n, i in self.inputs.items()}
            m.update(json.dumps(data, sort_keys=True).encode())
        if self.mounts:
            data = [m.id for m in self.mounts.values()]
            m.update(json.dumps(data).encode())
        return m.hexdigest()

    @property
    def dependencies(self) -> Generator[str, None, None]:
        """Return a list of pipeline ids this stage depends on"""

        for ip in self.inputs.values():

            if ip.origin != "org.osbuild.pipeline":
                continue

            for ref in ip.refs:
                yield ref

    def add_input(self, name, info, origin, options=None):
        ip = Input(name, info, origin, options or {})
        self.inputs[name] = ip
        return ip

    def add_device(self, name, info, parent, options):
        dev = Device(name, info, parent, options)
        self.devices[name] = dev
        return dev

    def add_mount(self, name, info, device, target, options):
        mount = Mount(name, info, device, target, options)
        self.mounts[name] = mount
        return mount

    def prepare_arguments(self, args, location):
        args["options"] = self.options
        args["meta"] = meta = {
            "id": self.id,
        }

        if self.source_epoch is not None:
            meta["source-epoch"] = self.source_epoch

        # Root relative paths: since paths are different on the
        # host and in the container they need to be mapped to
        # their path within the container. For all items that
        # have registered roots, re-root their path entries here
        for name, root in args.get("paths", {}).items():
            group = args.get(name)
            if not group or not isinstance(group, dict):
                continue
            for item in group.values():
                path = item.get("path")
                if not path:
                    continue
                item["path"] = os.path.join(root, path)

        with open(location, "w", encoding="utf-8") as fp:
            json.dump(args, fp)

    def run(self, tree, runner, build_tree, store, monitor, libdir, timeout=None):
        with contextlib.ExitStack() as cm:

            build_root = buildroot.BuildRoot(build_tree, runner, libdir, store.tmp)
            cm.enter_context(build_root)

            # if we have a build root, then also bind-mount the boot
            # directory from it, since it may contain efi binaries
            build_root.mount_boot = bool(self.build)

            # drop capabilities other than `DEFAULT_CAPABILITIES`
            build_root.caps = DEFAULT_CAPABILITIES | self.info.caps

            tmpdir = store.tempdir(prefix="buildroot-tmp-")
            tmpdir = cm.enter_context(tmpdir)

            inputs_tmpdir = os.path.join(tmpdir, "inputs")
            os.makedirs(inputs_tmpdir)
            inputs_mapped = "/run/osbuild/inputs"
            inputs = {}

            devices_mapped = "/dev"
            devices = {}

            mounts_tmpdir = os.path.join(tmpdir, "mounts")
            os.makedirs(mounts_tmpdir)
            mounts_mapped = "/run/osbuild/mounts"
            mounts = {}

            os.makedirs(os.path.join(tmpdir, "api"))
            args_path = os.path.join(tmpdir, "api", "arguments")

            args = {
                "tree": "/run/osbuild/tree",
                "paths": {
                    "devices": devices_mapped,
                    "inputs": inputs_mapped,
                    "mounts": mounts_mapped,
                },
                "devices": devices,
                "inputs": inputs,
                "mounts": mounts,
            }

            ro_binds = [
                f"{self.info.path}:/run/osbuild/bin/{self.name}",
                f"{inputs_tmpdir}:{inputs_mapped}",
                f"{args_path}:/run/osbuild/api/arguments"
            ]

            binds = [
                os.fspath(tree) + ":/run/osbuild/tree",
                f"{mounts_tmpdir}:{mounts_mapped}"
            ]

            storeapi = objectstore.StoreServer(store)
            cm.enter_context(storeapi)

            mgr = host.ServiceManager(monitor=monitor)
            cm.enter_context(mgr)

            ipmgr = InputManager(mgr, storeapi, inputs_tmpdir)
            for key, ip in self.inputs.items():
                data = ipmgr.map(ip)
                inputs[key] = data

            devmgr = DeviceManager(mgr, build_root.dev, tree)
            for name, dev in self.devices.items():
                devices[name] = devmgr.open(dev)

            mntmgr = MountManager(devmgr, mounts_tmpdir)
            for key, mount in self.mounts.items():
                data = mntmgr.mount(mount)
                mounts[key] = data

            self.prepare_arguments(args, args_path)

            api = API()
            build_root.register_api(api)

            rls = remoteloop.LoopServer()
            build_root.register_api(rls)

            extra_env = {}
            if self.source_epoch is not None:
                extra_env["SOURCE_DATE_EPOCH"] = str(self.source_epoch)

            r = build_root.run([f"/run/osbuild/bin/{self.name}"],
                               monitor,
                               timeout=timeout,
                               binds=binds,
                               readonly_binds=ro_binds,
                               extra_env=extra_env)

        return BuildResult(self, r.returncode, r.output, api.metadata, api.error)


class Pipeline:
    def __init__(self, name: str, runner=None, build=None, source_epoch=None):
        self.name = name
        self.build = build
        self.runner = runner
        self.stages: List[Stage] = []
        self.assembler = None
        self.source_epoch = source_epoch

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
        stage = Stage(info, sources_options, self.build,
                      self.id, options or {}, self.source_epoch)
        self.stages.append(stage)
        if self.assembler:
            self.assembler.base = stage.id
        return stage

    def build_stages(self, object_store, monitor, libdir, stage_timeout=None):
        results = {"success": True}

        # If there are no stages, just return here
        if not self.stages:
            return results

        # Check if the tree that we are supposed to build does
        # already exist. If so, short-circuit here
        if object_store.contains(self.id):
            return results

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

        # Not in the store yet, need to actually build it, but maybe
        # an intermediate checkpoint exists: Find the last stage that
        # already exists in the store and use that as the base.
        tree = None
        todo = collections.deque()
        for stage in reversed(self.stages):
            tree = object_store.get(stage.id)
            if tree:
                break
            todo.append(stage)  # append right side of the deque

        if not tree:
            tree = object_store.new()

        # If two run() calls race each-other, two trees will get built
        # and it is nondeterministic which of them will end up
        # referenced by the `tree_id` in the content store if they are
        # both committed. However, after the call to commit all the
        # trees will be based on the winner.
        results["stages"] = []

        while todo:
            stage = todo.pop()
            with build_tree.read() as build_path, tree.write() as path:

                monitor.stage(stage)

                r = stage.run(path,
                              self.runner,
                              build_path,
                              object_store,
                              monitor,
                              libdir,
                              stage_timeout)

                monitor.result(r)

            results["stages"].append(r)
            if not r.success:
                cleanup(build_tree, tree)
                results["success"] = False
                return results

            # The content of the tree now corresponds to the stage that
            # was build and this can can be identified via the id of it
            tree.id = stage.id

            if stage.checkpoint:
                object_store.commit(tree, stage.id)

        return results

    def run(self, store, monitor, libdir, stage_timeout=None):

        monitor.begin(self)

        results = self.build_stages(store,
                                    monitor,
                                    libdir,
                                    stage_timeout)

        monitor.finish(results)

        return results


class Manifest:
    """Representation of a pipeline and its sources"""

    def __init__(self):
        self.pipelines = collections.OrderedDict()
        self.sources: List[Source] = []

    def add_pipeline(
            self, name: str, runner: Optional[str], build: Optional[str] = None, source_epoch: Optional[int] = None
    ) -> Pipeline:
        pipeline = Pipeline(name, runner, build, source_epoch)
        if name in self.pipelines:
            raise ValueError(f"Name {name} already exists")
        self.pipelines[name] = pipeline
        return pipeline

    def add_source(self, info, items: List, options: Dict) -> Source:
        source = Source(info, items, options)
        self.sources.append(source)
        return source

    def download(self, store, monitor, libdir):
        with host.ServiceManager(monitor=monitor) as mgr:
            for source in self.sources:
                source.download(mgr, store, libdir)

    def depsolve(self, store: ObjectStore, targets: Iterable[str]) -> List[str]:
        """Return the list of pipelines that need to be built

        Given a list of target pipelines, return the names
        of all pipelines and their dependencies that are not
        already present in the store.
        """

        # A stack of pipelines to check if they need to be built
        check = list(map(self.get, targets))

        # The ordered result "set", will be reversed at the end
        build = collections.OrderedDict()

        while check:
            pl = check.pop()  # get the last(!) item

            if not pl:
                raise RuntimeError("Could not find pipeline.")

            if store.contains(pl.id):
                continue

            # The store does not have this pipeline, it needs to
            # be built, add it to the ordered result set and
            # ensure it is at the end, i.e. built before previously
            # checked items. NB: the result set is reversed before
            # it gets returned. This ensures that a dependency that
            # gets checked multiple times, like a build pipeline,
            # always gets built before its dependent pipeline.
            build[pl.id] = pl
            build.move_to_end(pl.id)

            # Add all dependencies to the stack of things to check,
            # starting with the build pipeline, if there is one
            if pl.build:
                check.append(self.get(pl.build))

            # Stages depend on other pipeline via pipeline inputs.
            # We check in reversed order until we hit a checkpoint
            for stage in reversed(pl.stages):

                # we stop if we have a checkpoint, i.e. we don't
                # need to build any stages after that checkpoint
                if store.contains(stage.id):
                    break

                pls = map(self.get, stage.dependencies)
                check.extend(pls)

        return list(map(lambda x: x.name, reversed(build.values())))

    def build(self, store, pipelines, monitor, libdir, stage_timeout=None):
        results = {"success": True}

        for pl in map(self.get, pipelines):
            res = pl.run(store, monitor, libdir, stage_timeout)
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
