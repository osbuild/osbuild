import abc
import os

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
            "items": self.items,
            "options": self.options,
            "cache": cache,
            "output": None,
            "checksums": [],
            "libdir": os.fspath(libdir)
        }

        client = mgr.start(f"source/{source}", self.info.path)

        reply = client.call("download", args)

        return reply


class SourceService(host.Service):
    """Source host service"""

    @abc.abstractmethod
    def download(self, items, cache, options):
        pass

    def dispatch(self, method: str, args, _fds):
        if method == "download":
            r = self.download(args["items"],
                              args["cache"],
                              args["options"])
            return r, None

        raise host.ProtocolError("Unknown method")
