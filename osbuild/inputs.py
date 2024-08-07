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
import contextlib
import hashlib
import json
import os
import tempfile
from typing import Any, Dict, Optional, Tuple

from osbuild import host
from osbuild.util.types import PathLike

from .objectstore import ObjectStore, StoreClient, StoreServer


class Input:
    """
    A single input with its corresponding options.
    """

    def __init__(self, name, info, origin: str, options: Dict):
        self.name = name
        self.info = info
        self.origin = origin
        self.refs: Dict[str, Dict[str, Any]] = {}
        self.options = options or {}
        self.id = self.calc_id()

    def add_reference(self, ref, options: Optional[Dict] = None):
        self.refs[ref] = options or {}
        self.id = self.calc_id()

    def calc_id(self):
        # NB: The input `name` is not included here on purpose since it
        # is either prescribed by the stage itself and thus not actual
        # parameter or arbitrary and chosen by the manifest generator
        # and thus can be changed without affecting the contents
        m = hashlib.sha256()
        m.update(json.dumps(self.info.name, sort_keys=True).encode())
        m.update(json.dumps(self.origin, sort_keys=True).encode())
        m.update(json.dumps(self.refs, sort_keys=True).encode())
        m.update(json.dumps(self.options, sort_keys=True).encode())
        return m.hexdigest()


class InputManager:
    def __init__(self, mgr: host.ServiceManager, storeapi: StoreServer, root: PathLike) -> None:
        self.service_manager = mgr
        self.storeapi = storeapi
        self.root = root
        self.inputs: Dict[str, Input] = {}

    def map(self, ip: Input, store: ObjectStore) -> Tuple[str, Dict]:

        target = os.path.join(self.root, ip.name)
        os.makedirs(target)

        args = {
            # mandatory bits
            "origin": ip.origin,
            "refs": ip.refs,

            "target": target,

            # global options
            "options": ip.options,

            # API endpoints
            "api": {
                "store": self.storeapi.socket_address
            }
        }

        with make_args_and_reply_files(store.tmp, args) as (fd_args, fd_reply):
            fds = [fd_args, fd_reply]
            client = self.service_manager.start(f"input/{ip.name}", ip.info.path)
            _, _ = client.call_with_fds("map", {}, fds)
            with os.fdopen(os.dup(fd_reply)) as f:
                reply = json.loads(f.read())

        path = reply["path"]

        if not path.startswith(self.root):
            raise RuntimeError(f"returned {path} has wrong prefix")

        reply["path"] = os.path.relpath(path, self.root)

        self.inputs[ip.name] = reply

        return reply


@contextlib.contextmanager
def make_args_and_reply_files(tmp, args):
    with tempfile.TemporaryFile("w+", dir=tmp, encoding="utf-8") as f_args, \
            tempfile.TemporaryFile("w+", dir=tmp, encoding="utf-8") as f_reply:
        json.dump(args, f_args)
        f_args.seek(0)
        yield f_args.fileno(), f_reply.fileno()


class InputService(host.Service):
    """Input host service"""

    @abc.abstractmethod
    def map(self, store, origin, refs, target, options):
        pass

    def unmap(self):
        pass

    def stop(self):
        self.unmap()

    def dispatch(self, method: str, _, fds):
        if method == "map":
            # map() sends fd[0] to read the arguments from and fd[1] to
            # write the reply back. This avoids running into EMSGSIZE
            with os.fdopen(fds.steal(0)) as f:
                args = json.load(f)
            store = StoreClient(connect_to=args["api"]["store"])
            r = self.map(store,
                         args["origin"],
                         args["refs"],
                         args["target"],
                         args["options"])
            with os.fdopen(fds.steal(1), "w") as f:
                f.write(json.dumps(r))
                f.seek(0)
            return "{}", None

        raise host.ProtocolError("Unknown method")
