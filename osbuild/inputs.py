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


import hashlib
import importlib
import json
import os
import subprocess

from typing import Dict, Optional, Tuple

from osbuild.util.types import PathLike
from .objectstore import StoreServer


class Input:
    """
    A single input with its corresponding options.
    """

    def __init__(self, name, info, origin: str, options: Dict):
        self.name = name
        self.info = info
        self.origin = origin
        self.refs = {}
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

    def run(self, storeapi: StoreServer, root: PathLike) -> Tuple[str, Dict]:
        name = self.info.name

        target = os.path.join(root, self.name)
        os.makedirs(target)

        msg = {
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

        # We want the `osbuild` python package that contains this
        # very module, which might be different from the system wide
        # installed one, to be accessible to the Input programs so
        # we detect our origin and set the `PYTHONPATH` accordingly
        modorigin = importlib.util.find_spec("osbuild").origin
        modpath = os.path.dirname(modorigin)
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.dirname(modpath)

        r = subprocess.run([self.info.path],
                           env=env,
                           input=json.dumps(msg),
                           stdout=subprocess.PIPE,
                           encoding="utf-8",
                           check=False)

        try:
            reply = json.loads(r.stdout)
        except ValueError:
            raise RuntimeError(f"{name}: error: {r.stderr}") from None

        if "error" in reply:
            raise RuntimeError(f"{name}: " + reply["error"])

        if r.returncode != 0:
            raise RuntimeError(f"{name}: error {r.returncode}")

        path = reply["path"]

        if not path.startswith(root):
            raise RuntimeError(f"returned {path} has wrong prefix")

        reply["path"] = os.path.relpath(path, root)

        return reply
