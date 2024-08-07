import abc
import hashlib
import json
import os
import tempfile
from typing import ClassVar, Dict

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
        # compat with pipeline
        self.build = None
        self.runner = None
        self.source_epoch = None

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

    # "name", "id", "stages", "results" is only here to make it looks like a
    # pipeline for the monitor. This should be revisited at some point
    # and maybe the monitor should get first-class support for
    # sources?
    #
    # In any case, sources can be represented only poorly right now
    # by the monitor because the source is called with download()
    # for all items and there is no way for a stage right now to
    # report something structured back to the host that runs the
    # source so it just downloads all sources without any user
    # visible progress right now
    @property
    def name(self):
        return f"source {self.info.name}"

    @property
    def id(self):
        m = hashlib.sha256()
        m.update(json.dumps(self.info.name, sort_keys=True).encode())
        m.update(json.dumps(self.items, sort_keys=True).encode())
        return m.hexdigest()

    @property
    def stages(self):
        return []


class SourceService(host.Service):
    """Source host service"""

    max_workers = 1

    content_type: ClassVar[str]
    """The content type of the source."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache = None
        self.options = None
        self.tmpdir = None

    @abc.abstractmethod
    def fetch_one(self, checksum, desc) -> None:
        """Performs the actual fetch of an element described by its checksum and its descriptor"""

    @abc.abstractmethod
    def fetch_all(self, items: Dict) -> None:
        """Fetch all sources."""

    def exists(self, checksum, _desc) -> bool:
        """Returns True if the item to download is in cache. """
        return os.path.isfile(f"{self.cache}/{checksum}")

    def setup(self, args):
        self.cache = os.path.join(args["cache"], self.content_type)
        os.makedirs(self.cache, exist_ok=True)
        self.options = args["options"]

    def dispatch(self, method: str, args, fds):
        if method == "download":
            self.setup(args)
            with tempfile.TemporaryDirectory(prefix=".unverified-", dir=self.cache) as self.tmpdir:
                self.fetch_all(args["items"])
                return None, None

        raise host.ProtocolError("Unknown method")
