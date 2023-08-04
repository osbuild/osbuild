import contextlib
import hashlib
import json
import os
from typing import Generator

import osbuild.service as service

from .. import buildroot, objectstore, remoteloop
from ..api import API
from ..service.device import Device, DeviceManager
from ..service.input import Input, InputManager
from ..service.mount import Mount, MountManager

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

            build_root = buildroot.BuildRoot(build_tree, runner.path, libdir, store.tmp)
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

            meta = cm.enter_context(
                tree.meta.write(self.id)
            )

            ro_binds = [
                f"{self.info.path}:/run/osbuild/bin/{self.name}",
                f"{inputs_tmpdir}:{inputs_mapped}",
                f"{args_path}:/run/osbuild/api/arguments"
            ]

            binds = [
                os.fspath(tree) + ":/run/osbuild/tree",
                meta.name + ":/run/osbuild/meta",
                f"{mounts_tmpdir}:{mounts_mapped}"
            ]

            storeapi = objectstore.StoreServer(store)
            cm.enter_context(storeapi)

            mgr = service.ServiceManager(monitor=monitor)
            cm.enter_context(mgr)

            ipmgr = InputManager(mgr, storeapi, inputs_tmpdir)
            for key, ip in self.inputs.items():
                data = ipmgr.map(ip, store)
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

        return BuildResult(self, r.returncode, r.output, api.error)


class BuildResult:
    def __init__(self, origin, returncode, output, error):
        self.name = origin.name
        self.id = origin.id
        self.success = returncode == 0
        self.output = output
        self.error = error

    def as_dict(self):
        return vars(self)
