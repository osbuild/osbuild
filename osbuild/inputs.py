"""
Pipeline inputs

A pipeline input provides data in various forms to a `Stage`, like
files, OSTree commits or trees. The content can either be obtained
via a `Source` or have been built by a `Pipeline`. Thus an `Input`
is the bridge between various types of content that originate from
different types of sources.

The acceptable origin of the data is determined by the `Input`
itself. What types of input are allowed and required is determined
by the `Stage`.

To osbuild itself this is all transparent. The only data visible to
osbuild is the path. The input options are just passed to the
`Input` as is and the result is forwarded to the `Stage`.
"""

import abc
import hashlib
import json
import os

from typing import Dict, Optional, Tuple

from osbuild import host
from osbuild.util.types import PathLike
from .objectstore import StoreClient, StoreServer


class Input:
    """
    A single input with its corresponding options.
    """

    def __init__(self, info, name, origin: str, options: Dict):
        self.info = info
        self.name = name
        self.origin = origin
        self.refs = {}
        self.options = options or {}
        self.id = self.calc_id()

    def add_reference(self, ref, options: Optional[Dict] = None):
        self.refs[ref] = options or {}
        self.id = self.calc_id()

    def calc_id(self):
        m = hashlib.sha256()
        m.update(json.dumps(self.info.name, sort_keys=True).encode())
        m.update(json.dumps(self.name, sort_keys=True).encode())
        m.update(json.dumps(self.origin, sort_keys=True).encode())
        m.update(json.dumps(self.refs, sort_keys=True).encode())
        m.update(json.dumps(self.options, sort_keys=True).encode())
        return m.hexdigest()

    def run(self,
            mgr: host.ServiceManager,
            storeapi: StoreServer,
            root: PathLike) -> Tuple[str, Dict]:

        target = os.path.join(root, self.name)
        os.makedirs(target)

        args = {
            # mandatory bits
            "origin": self.origin,
            "refs": self.refs,

            "target": target,

            # global options
            "options": self.options,

            # API endpoints
            "api": {
                "store": storeapi.socket_address
            }
        }

        client = mgr.start(f"input/{self.name}", self.info.path)
        reply = client.call("map", args)

        path, data = reply["path"], reply.get("data", None)

        if not path.startswith(root):
            raise RuntimeError(f"returned {path} has wrong prefix")

        path = os.path.relpath(path, root)

        return path, data


class InputService(host.Service):
    """Input host service"""

    @abc.abstractmethod
    def map(self, store, origin, refs, target, options):
        pass

    def unmap(self):
        pass

    def stop(self):
        self.unmap()

    def dispatch(self, method: str, args, _fds):
        if method == "map":
            store = StoreClient(connect_to=args["api"]["store"])
            r = self.map(store,
                         args["origin"],
                         args["refs"],
                         args["target"],
                         args["options"])
            return r, None

        raise host.ProtocolError("Unknown method")
