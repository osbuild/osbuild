"""
Device Handling for pipeline stages

Specific type of artifacts require device support, such as
loopback devices or device mapper. Since stages are always
run in a container and are isolated from the host, they do
not have direct access to devices and specifically can not
setup new ones.
Therefore device handling is done at the osbuild level with
the help of a device host services. Device specific modules
provide the actual functionality and thus the core device
support in osbuild itself is abstract.
"""

import abc
import hashlib
import json
import os

from typing import Dict, Optional, Any

from osbuild import host


class Device:
    """
    A single device with its corresponding options
    """

    def __init__(self, name, info, parent, options: Dict):
        self.name = name
        self.info = info
        self.parent = parent
        self.options = options or {}
        self.id = self.calc_id()

    def calc_id(self):
        # NB: Since the name of the device is arbitrary or prescribed
        # by the stage, it is not included in the id calculation.
        m = hashlib.sha256()

        m.update(json.dumps(self.info.name, sort_keys=True).encode())
        if self.parent:
            m.update(json.dumps(self.parent.id, sort_keys=True).encode())
        m.update(json.dumps(self.options, sort_keys=True).encode())
        return m.hexdigest()


class DeviceManager:
    """Manager for Devices

    Uses a `host.ServiceManager` to open `Device` instances.
    """

    def __init__(self, mgr: host.ServiceManager, devpath: str, tree: str) -> None:
        self.service_manager = mgr
        self.devpath = devpath
        self.tree = tree
        self.devices: Dict[str, Dict[str, Any]] = {}

    def device_relpath(self, dev: Optional[Device]) -> Optional[str]:
        if dev is None:
            return None
        return self.devices[dev.name]["path"]

    def device_abspath(self, dev: Optional[Device]) -> Optional[str]:
        relpath = self.device_relpath(dev)
        if relpath is None:
            return None
        return os.path.join(self.devpath, relpath)

    def open(self, dev: Device) -> Dict:

        parent = self.device_relpath(dev.parent)

        args = {
            # global options
            "dev": self.devpath,
            "tree": self.tree,

            "parent": parent,

            # per device options
            "options": dev.options,
        }

        mgr = self.service_manager

        client = mgr.start(f"device/{dev.name}", dev.info.path)
        res = client.call("open", args)

        self.devices[dev.name] = res
        return res


class DeviceService(host.Service):
    """Device host service"""

    @abc.abstractmethod
    def open(self, devpath: str, parent: str, tree: str, options: Dict):
        """Open a specific device

        This method must be implemented by the specific device service.
        It should open the device and create a device node in `devpath`.
        The return value must contain the relative path to the device
        node.
        """

    @abc.abstractmethod
    def close(self):
        """Close the device"""

    def stop(self):
        self.close()

    def dispatch(self, method: str, args, _fds):
        if method == "open":
            r = self.open(args["dev"],
                          args["parent"],
                          args["tree"],
                          args["options"])
            return r, None
        if method == "close":
            r = self.close()
            return r, None

        raise host.ProtocolError("Unknown method")
