import abc
import contextlib
import os
import json
import tempfile

from . import host
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

    def download(self, mgr: host.ServiceManager, store: ObjectStore, libdir: PathLike):
        source = self.info.name
        cache = os.path.join(store.store, "sources")

        args = {
            "options": self.options,
            "cache": cache,
            "output": None,
            "checksums": [],
            "libdir": os.fspath(libdir)
        }

        client = mgr.start(f"source/{source}", self.info.path)

        with self.make_items_file(store.tmp) as fd:
            fds = [fd]
            reply = client.call_with_fds("download", args, fds)

        return reply

    @contextlib.contextmanager
    def make_items_file(self, tmp):
        with tempfile.TemporaryFile("w+", dir=tmp, encoding="utf-8") as f:
            json.dump(self.items, f)
            f.seek(0)
            yield f.fileno()


class SourceService(host.Service):
    """Source host service"""

    @abc.abstractmethod
    def download(self, items, cache, options):
        pass

    def dispatch(self, method: str, args, fds):
        if method == "download":
            with os.fdopen(fds.steal(0)) as f:
                items = json.load(f)

            r = self.download(items,
                              args["cache"],
                              args["options"])
            return r, None

        raise host.ProtocolError("Unknown method")
