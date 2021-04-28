import os
import importlib
import json
import subprocess

from .objectstore import ObjectStore
from .util.types import PathLike


class Source:
    """
    A single source with is corresponding options.
    """

    def __init__(self, info, items, options) -> None:
        self.info = info
        self.items = items or {}
        self.options = options

    def download(self, store: ObjectStore, libdir: PathLike):
        source = self.info.name
        cache = os.path.join(store.store, "sources")
        msg = {
            "items": self.items,
            "options": self.options,
            "cache": cache,
            "output": None,
            "checksums": [],
            "libdir": os.fspath(libdir)
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
            raise RuntimeError(f"{source}: error: {r.stderr}") from None

        if "error" in reply:
            raise RuntimeError(f"{source}: " + reply["error"])

        if r.returncode != 0:
            raise RuntimeError(f"{source}: error {r.returncode}")
