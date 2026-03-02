import collections
import contextlib
import hashlib
import json
import os
import traceback
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, Iterator, List, Optional

from . import buildroot, host, objectstore, remoteloop
from .api import API
from .devices import Device, DeviceManager
from .inputs import Input, InputManager
from .mounts import Mount, MountManager
from .objectstore import ObjectStore
from .qemu import Qemu
from .sources import Source
from .util import experimentalflags, osrelease

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
    def __init__(self, origin: 'Stage', returncode: int, output: str, error: Dict[str, str]) -> None:
        self.name = origin.name
        self.id = origin.id
        self.success = returncode == 0
        self.output = output
        self.error = error

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "id": self.id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BuildResult":
        result = cls.__new__(cls)
        result.name = data["name"]
        result.id = data["id"]
        result.success = data["success"]
        result.output = data["output"]
        result.error = data["error"]
        return result


class DownloadResult:
    def __init__(self, name: str, source_id: str, success: bool) -> None:
        self.name = name
        self.id = source_id
        self.success = success
        self.output = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "id": self.id,
            "success": self.success,
            "output": self.output,
        }


# pylint: disable=too-many-instance-attributes
class Stage:
    def __init__(self, info, source_options, build, base, options, source_epoch):
        self.info_name = info.name
        self.info_path = info.path
        self.info_caps = info.caps
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
    def name(self) -> str:
        return self.info_name

    @property
    def id(self) -> str:
        m = hashlib.sha256()
        m.update(json.dumps(self.name, sort_keys=True).encode())
        m.update(json.dumps(self.build, sort_keys=True).encode())
        m.update(json.dumps(self.base, sort_keys=True).encode())
        m.update(json.dumps(self.options, sort_keys=True).encode())
        if self.source_epoch is not None:
            m.update(json.dumps(self.source_epoch, sort_keys=True).encode())
        if self.inputs:
            data_inp = {n: i.id for n, i in self.inputs.items()}
            m.update(json.dumps(data_inp, sort_keys=True).encode())
        if self.mounts:
            data_mnt = [m.id for m in self.mounts.values()]
            m.update(json.dumps(data_mnt).encode())
        return m.hexdigest()

    @property
    def dependencies(self) -> Generator[str, None, None]:
        """Return a list of pipeline ids this stage depends on"""

        for ip in self.inputs.values():

            if ip.origin != "org.osbuild.pipeline":
                continue

            yield from ip.refs

    def add_input(self, name, info, origin, options=None):
        ip = Input(name, info, origin, options or {})
        self.inputs[name] = ip
        return ip

    def add_device(self, name, info, parent, options):
        dev = Device(name, info, parent, options)
        self.devices[name] = dev
        return dev

    def add_mount(self, name, info, device, partition, target, options):
        mount = Mount(name, info, device, partition, target, options)
        self.mounts[name] = mount
        return mount

    def to_dict(self, libdir):
        return {
            "info_name": self.info_name,
            "info_path": str(Path(self.info_path).relative_to(libdir)),
            "info_caps": list(self.info_caps),
            "sources": self.sources,
            "build": self.build,
            "base": self.base,
            "options": self.options,
            "source_epoch": self.source_epoch,
            "checkpoint": self.checkpoint,
            "inputs": {name: inp.to_dict(libdir) for name, inp in self.inputs.items()},
            "devices": {name: dev.to_dict(libdir) for name, dev in self.devices.items()},
            "mounts": {name: mnt.to_dict(libdir) for name, mnt in self.mounts.items()},
        }

    @classmethod
    def from_dict(cls, data, libdir):
        class InfoStub:
            def __init__(self, name: str, path: str, caps: set):
                self.name = name
                self.path = path
                self.caps = caps

        info = InfoStub(data["info_name"], Path(libdir) / data["info_path"], set(data["info_caps"]))
        stage = cls(
            info=info,
            source_options=data["sources"],
            build=data["build"],
            base=data["base"],
            options=data["options"],
            source_epoch=data["source_epoch"]
        )
        stage.checkpoint = data["checkpoint"]

        for name, inp_data in data["inputs"].items():
            inp = Input.from_dict(inp_data, libdir)
            stage.inputs[name] = inp

        devices_by_name = {}
        for name, dev_data in data["devices"].items():
            parent = devices_by_name.get(dev_data["parent_name"]) if dev_data["parent_name"] else None
            dev = Device.from_dict(dev_data, libdir, parent)
            stage.devices[name] = dev
            devices_by_name[name] = dev

        for name, mnt_data in data["mounts"].items():
            device = stage.devices.get(mnt_data["device_name"]) if mnt_data["device_name"] else None
            mnt = Mount.from_dict(mnt_data, libdir, device)
            stage.mounts[name] = mnt

        return stage

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

    def run(
            self,
            tree_path,
            meta_name,
            runner,
            build_tree,
            store,
            monitor,
            libdir,
            debug_break="",
            timeout=None) -> BuildResult:
        with contextlib.ExitStack() as cm:

            build_root = buildroot.BuildRoot(build_tree, runner.path, libdir, store.tmp)
            cm.enter_context(build_root)

            # if we have a build root, then also bind-mount the boot
            # directory from it, since it may contain efi binaries
            build_root.mount_boot = bool(self.build)

            # drop capabilities other than `DEFAULT_CAPABILITIES`
            build_root.caps = DEFAULT_CAPABILITIES | self.info_caps

            tmpdir = store.tempdir(prefix="buildroot-tmp-")
            tmpdir = cm.enter_context(tmpdir)

            inputs_tmpdir = os.path.join(tmpdir, "inputs")
            os.makedirs(inputs_tmpdir)
            inputs_mapped = "/run/osbuild/inputs"
            inputs: Dict[Any, Any] = {}

            devices_mapped = "/dev"
            devices: Dict[Any, Any] = {}

            mounts_tmpdir = os.path.join(tmpdir, "mounts")
            os.makedirs(mounts_tmpdir)
            mounts_mapped = "/run/osbuild/mounts"
            mounts: Dict[Any, Any] = {}

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
                f"{self.info_path}:/run/osbuild/bin/{self.name}",
                f"{inputs_tmpdir}:{inputs_mapped}",
                f"{args_path}:/run/osbuild/api/arguments"
            ]

            binds = [
                tree_path + ":/run/osbuild/tree",
                meta_name + ":/run/osbuild/meta",
                f"{mounts_tmpdir}:{mounts_mapped}"
            ]

            storeapi = objectstore.StoreServer(store)
            cm.enter_context(storeapi)

            mgr = host.ServiceManager(monitor=monitor)
            cm.enter_context(mgr)

            ipmgr = InputManager(mgr, storeapi, inputs_tmpdir)
            for key, ip in self.inputs.items():
                data_inp = ipmgr.map(ip)
                inputs[key] = data_inp

            devmgr = DeviceManager(mgr, build_root.dev, tree_path)
            for name, dev in self.devices.items():
                devices[name] = devmgr.open(dev)

            mntmgr = MountManager(devmgr, mounts_tmpdir)
            for key, mount in self.mounts.items():
                data_mnt = mntmgr.mount(mount)
                mounts[key] = data_mnt

            self.prepare_arguments(args, args_path)

            api = API()
            build_root.register_api(api)

            rls = remoteloop.LoopServer()
            build_root.register_api(rls)

            extra_env = {}
            if self.source_epoch is not None:
                extra_env["SOURCE_DATE_EPOCH"] = str(self.source_epoch)
            if experimentalflags.get_bool("debug-qemu-user"):
                extra_env["QEMU_LOG"] = "unimp"

            debug_shell = debug_break in ('*', self.name, self.id)

            r = build_root.run([f"/run/osbuild/bin/{self.name}"],
                               monitor,
                               timeout=timeout,
                               binds=binds,
                               readonly_binds=ro_binds,
                               extra_env=extra_env,
                               debug_shell=debug_shell)

        return BuildResult(self, r.returncode, r.output, api.error)


class Runner:
    def __init__(self, info, name: Optional[str] = None) -> None:
        self.info_path = info.path
        self.name = name or os.path.basename(info.path)

    @property
    def path(self):
        return self.info_path

    @property
    def exec(self):
        return os.path.basename(self.info_path)

    def to_dict(self, libdir):
        info_path_rel = Path(self.info_path).relative_to(libdir)
        return {
            "name": self.name,
            "info_path": str(info_path_rel),
        }

    @classmethod
    def from_dict(cls, data, libdir):
        info_path_abs = str(Path(libdir) / data["info_path"])

        class InfoStub:
            def __init__(self, path):
                self.path = path

        info = InfoStub(info_path_abs)
        return cls(info, data["name"])


# pylint: disable=too-many-branches
class Pipeline:
    def __init__(self, name: str, runner: Runner, build=None, source_epoch=None):
        self.name = name
        self.build = build
        self.runner = runner
        self.stages: List[Stage] = []
        self.assembler = None
        self.source_epoch = source_epoch
        self.run_in_vm = False

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

    def build_stages(self, object_store, monitor, libdir,
                     debug_break="", stage_timeout=None, in_vm=False):
        results = {"success": True, "name": self.name}

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
            build_tree = object_store.host_tree
        else:
            build_tree = object_store.get(self.build)

        if not build_tree:
            raise AssertionError(f"build tree {self.build} not found")

        # Not in the store yet, need to actually build it, but maybe
        # an intermediate checkpoint exists: Find the last stage that
        # already exists in the store and use that as the base.
        tree = object_store.new(self.id)
        tree.source_epoch = self.source_epoch

        todo = collections.deque()
        for stage in reversed(self.stages):
            base = object_store.get(stage.id)
            if base:
                tree.init(base)
                break
            todo.append(stage)  # append right side of the deque

        # If two run() calls race each-other, two trees will get built
        # and it is nondeterministic which of them will end up
        # referenced by the `tree_id` in the content store if they are
        # both committed. However, after the call to commit all the
        # trees will be based on the winner.
        results["stages"] = []

        with contextlib.ExitStack() as cm:
            qemu = None
            tree_dir = os.path.join(tree.path, "tree")
            if in_vm:
                buildtree_dir = os.path.join(build_tree.path, "tree")

                qemu = Qemu("3G",
                            buildtree_dir,
                            libdir)
                qemu.add_virtiofs(object_store.store, "store", readonly=False)

                cm.enter_context(qemu)

                # Update the object store in the VM to match
                # the active floating objects
                qemu.monitored_request(monitor, "update_store",
                                       floating=object_store.export_floating())

            while todo:
                stage = todo.pop()

                monitor.stage(stage)

                with tree.meta.write(stage.id) as meta:
                    if qemu:
                        resp = qemu.monitored_request(monitor, "run_stage",
                                                      stage=stage.to_dict(libdir),
                                                      runner=self.runner.to_dict(libdir),
                                                      tree_dir=str(Path(tree_dir).relative_to(object_store.store)),
                                                      meta_name=str(Path(meta.name).relative_to(object_store.store)),
                                                      build_tree=build_tree.id,
                                                      debug_break=debug_break,
                                                      stage_timeout=stage_timeout)
                        r = BuildResult.from_dict(resp)
                    else:
                        r = stage.run(os.fspath(tree),
                                      meta.name,
                                      self.runner,
                                      build_tree,
                                      object_store,
                                      monitor,
                                      libdir,
                                      debug_break,
                                      stage_timeout)

                md = tree.meta.get(r.id)
                monitor.result(r, md)

                results["stages"].append(r)
                if not r.success:
                    cleanup(build_tree, tree)
                    results["success"] = False
                    return results

                if stage.checkpoint:
                    object_store.commit(tree, stage.id)

        tree.finalize()

        return results

    def run(self, store, monitor, libdir, debug_break="", stage_timeout=None, in_vm=False):

        self.run_in_vm = in_vm
        monitor.begin(self)

        try:
            results = self.build_stages(store,
                                        monitor,
                                        libdir,
                                        debug_break,
                                        stage_timeout,
                                        in_vm)

            monitor.finish(results)

            return results
        except Exception as e:
            monitor.log(
                str(e),
                origin="osbuild.pipeline",
                error={
                    "type": "exception",
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                },
            )
            raise


class Manifest:
    """Representation of a pipeline and its sources"""

    def __init__(self):
        self.metadata = {}
        self.pipelines = collections.OrderedDict()
        self.sources = []

    def add_metadata(self, name: str, data: Dict[str, Any]) -> None:
        self.metadata[name] = data

    def add_pipeline(
        self,
        name: str,
        runner: Runner,
        build: Optional[str] = None,
        source_epoch: Optional[int] = None
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

    def download(self, store, monitor):
        with host.ServiceManager(monitor=monitor) as mgr:
            for source in self.sources:
                # Workaround for lack of progress from sources, this
                # will need to be reworked later.
                dr = DownloadResult(source.name, source.id, success=True)
                monitor.begin(source)
                try:
                    source.download(mgr, store)
                except host.RemoteError as e:
                    dr.success = False
                    dr.output = str(e)
                    monitor.result(dr)
                    raise e
                monitor.result(dr)
                # ideally we would make the whole of download more symmetric
                # to "build_stages" and return a "results" here in "finish"
                # as well
                monitor.finish({"name": source.info_name})

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

    def build(self, store, pipelines, monitor, libdir,
              debug_break="", stage_timeout=None, in_vm=None) -> Dict[str, Any]:
        """Build the manifest

        Returns a dict of string keys that contains the overall
        "success" and the `BuildResult` of each individual pipeline.

        The overall success "success" is stored as the string "success"
        with the bool result and the build pipelines BuildStatus is
        stored under the pipelines ID string.
        """
        results = {"success": True}

        for name_or_id in pipelines:
            pl = self[name_or_id]
            res = pl.run(store, monitor, libdir, debug_break, stage_timeout, in_vm=in_vm and pl.name in in_vm)
            results[pl.id] = res
            if not res["success"]:
                results["success"] = False
                return results

        return results

    def mark_checkpoints(self, patterns):
        """Match pipeline names, stage ids, and stage names against an iterable
        of `fnmatch`-patterns."""
        selected = []

        def matching(haystack):
            return any(fnmatch(haystack, p) for p in patterns)

        for pipeline in self.pipelines.values():
            # checkpoints are marked on stages, if a pipeline has no stages we
            # can't mark it
            if not pipeline.stages:
                continue

            if matching(pipeline.name):
                selected.append(pipeline.name)
                pipeline.stages[-1].checkpoint = True

            for stage in pipeline.stages:
                if matching(stage.id) or matching(stage.name):
                    selected.append(stage.id)
                    stage.checkpoint = True

        return selected

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
        raise KeyError(f"'{name_or_id}' not found in manifest pipelines: {list(self.pipelines.keys())}")

    def __iter__(self) -> Iterator[Pipeline]:
        return iter(self.pipelines.values())


def detect_host_runner():
    """Use os-release(5) to detect the runner for the host"""
    osname = osrelease.describe_os(*osrelease.DEFAULT_PATHS)
    return "org.osbuild." + osname
