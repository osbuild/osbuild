import os
import importlib
import json
import subprocess

from . import api
from .objectstore import ObjectStore
from .util import jsoncomm
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
        cache = os.path.join(store.store, "sources", source)
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


class SourcesServer(api.BaseAPI):

    endpoint = "sources"

    def __init__(self, libdir, options, cache, output, *, socket_address=None):
        super().__init__(socket_address)
        self.libdir = libdir
        self.cache = cache
        self.output = output
        self.options = options or {}

    def _run_source(self, source, checksums):
        msg = {
            "items": {},
            "options": self.options.get(source, {}),
            "cache": f"{self.cache}/{source}",
            "output": f"{self.output}/{source}",
            "checksums": checksums,
            "libdir": self.libdir
        }

        r = subprocess.run(
            [f"{self.libdir}/sources/{source}"],
            input=json.dumps(msg),
            stdout=subprocess.PIPE,
            encoding="utf-8",
            check=False)

        try:
            return json.loads(r.stdout)
        except ValueError:
            return {"error": f"source returned malformed json: {r.stdout}"}

    def _message(self, msg, fds, sock):
        reply = self._run_source(msg["source"], msg["checksums"])
        sock.send(reply)


def get(source, checksums, api_path="/run/osbuild/api/sources"):
    with jsoncomm.Socket.new_client(api_path) as client:
        msg = {
            "source": source,
            "checksums": checksums
        }
        client.send(msg)
        reply, _, _ = client.recv()
        if "error" in reply:
            raise RuntimeError(f"{source}: " + reply["error"])
        return reply
