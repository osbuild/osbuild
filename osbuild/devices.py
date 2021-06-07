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

from typing import Dict

from osbuild import host


class Device:
    """
    A single device with its corresponding options
    """

    def __init__(self, name, info, options: Dict):
        self.name = name
        self.info = info
        self.options = options or {}
        self.id = self.calc_id()

    def calc_id(self):
        # NB: Since the name of the device is arbitrary or prescribed
        # by the stage, it is not included in the id calculation.
        m = hashlib.sha256()
        m.update(json.dumps(self.info.name, sort_keys=True).encode())
        m.update(json.dumps(self.options, sort_keys=True).encode())
        return m.hexdigest()

    def open(self, mgr: host.ServiceManager, dev: str, tree: str) -> Dict:
        args = {
            # global options
            "dev": dev,
            "tree": tree,

            # per device options
            "options": self.options,
        }

        client = mgr.start(f"device/{self.name}", self.info.path)
        res = client.call("open", args)

        return res


class DeviceService(host.Service):
    """Device host service"""

    @abc.abstractmethod
    def open(self, devpath: str, tree: str, options: Dict):
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
            r = self.open(args["dev"], args["tree"], args["options"])
            return r, None

        raise host.ProtocolError("Unknown method")
