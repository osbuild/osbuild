"""
Mount Handling for pipeline stages

Allows stages to access file systems provided by devices.
This makes mount handling transparent to the stages, i.e.
the individual stages do not need any code for different
file system types and the underlying devices.
"""

import abc
import hashlib
import json
import os
import subprocess

from typing import Dict

from osbuild import host
from osbuild.devices import DeviceManager


class Mount:
    """
    A single mount with its corresponding options
    """

    def __init__(self, name, info, device, target, options: Dict):
        self.name = name
        self.info = info
        self.device = device
        self.target = target
        self.options = options
        self.id = self.calc_id()

    def calc_id(self):
        m = hashlib.sha256()
        m.update(json.dumps(self.info.name, sort_keys=True).encode())
        if self.device:
            m.update(json.dumps(self.device.id, sort_keys=True).encode())
        if self.target:
            m.update(json.dumps(self.target, sort_keys=True).encode())
        m.update(json.dumps(self.options, sort_keys=True).encode())
        return m.hexdigest()


class MountManager:
    """Manager for Mounts

    Uses a `host.ServiceManager` to activate `Mount` instances.
    Takes a `DeviceManager` to access devices and a directory
    called `root`, which is the root of all the specified mount
    points.
    """

    def __init__(self, devices: DeviceManager, root: str) -> None:
        self.devices = devices
        self.root = root
        self.mounts = {}

    def mount(self, mount: Mount) -> Dict:

        source = self.devices.device_abspath(mount.device)

        args = {
            "source": source,
            "root": self.root,
            "target": mount.target,

            "options": mount.options,
        }

        mgr = self.devices.service_manager

        client = mgr.start(f"mount/{mount.name}", mount.info.path)
        path = client.call("mount", args)

        if not path.startswith(self.root):
            raise RuntimeError(f"returned path '{path}' has wrong prefix")

        path = os.path.relpath(path, self.root)

        self.mounts[mount.name] = path

        return {"path": path}


class MountService(host.Service):
    """Mount host service"""

    def __init__(self, args):
        super().__init__(args)

        self.mountpoint = None
        self.check = False

    @abc.abstractmethod
    def translate_options(self, options: Dict):
        return []

    def mount(self, source: str, root: str, target: str, options: Dict):

        mountpoint = os.path.join(root, target.lstrip("/"))
        args = self.translate_options(options)

        os.makedirs(mountpoint, exist_ok=True)
        self.mountpoint = mountpoint

        subprocess.run(
            ["mount"] +
            args + [
                "--source", source,
                "--target", mountpoint
            ],
            check=True)

        self.check = True
        return mountpoint

    def umount(self):
        if not self.mountpoint:
            return

        self.sync()

        print("umounting")

        # We ignore errors here on purpose
        subprocess.run(["umount", self.mountpoint],
                       check=self.check)
        self.mountpoint = None

    def sync(self):
        subprocess.run(["sync", "-f", self.mountpoint],
                       check=self.check)

    def stop(self):
        self.umount()

    def dispatch(self, method: str, args, _fds):
        if method == "mount":
            r = self.mount(args["source"],
                           args["root"],
                           args["target"],
                           args["options"])
            return r, None

        raise host.ProtocolError("Unknown method")
