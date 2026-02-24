import abc
import hashlib
import json
import os
import shutil
import tempfile
from typing import ClassVar, Dict

from . import host
from .objectstore import ObjectStore


class Source:
    """
    A single source with is corresponding options.
    """

    def __init__(self, info, items, options) -> None:
        self.info_name = info.name
        self.info_path = info.path
        self.items = items or {}
        self.options = options
        # compat with pipeline
        self.build = None
        self.runner = None
        self.source_epoch = None

    def download(self, mgr: host.ServiceManager, store: ObjectStore):
        source = self.info_name
        cache = os.path.join(store.store, "sources")

        args = {
            "items": self.items,
            "options": self.options,
            "cache": cache,
            "output": None,
            "checksums": [],
        }

        client = mgr.start(f"source/{source}", self.info_path)
        reply = client.call("download", args)

        return reply

    def copy(self, mgr: host.ServiceManager, store: ObjectStore, dst_store: ObjectStore):
        source = self.info_name
        cache = os.path.join(store.store, "sources")
        dst_cache = os.path.join(dst_store.store, "sources")

        args = {
            "items": self.items,
            "options": self.options,
            "cache": cache,
            "dst_cache": dst_cache,
            "checksums": [],
        }

        client = mgr.start(f"source/{source}", self.info_path)
        reply = client.call("copy", args)

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
        return f"source {self.info_name}"

    @property
    def id(self):
        m = hashlib.sha256()
        m.update(json.dumps(self.info_name, sort_keys=True).encode())
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

    def copy_all(self, items: Dict, dst_cache: str) -> None:
        """Copies the source to the destination"""
        target_dir = os.path.join(dst_cache, self.content_type)
        os.makedirs(target_dir, exist_ok=True)
        for item in items:
            shutil.copy2(os.path.join(self.cache, item), os.path.join(target_dir, item))

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

        elif method == "copy":
            self.setup(args)
            self.copy_all(args["items"], args["dst_cache"])
            return None, None

        raise host.ProtocolError("Unknown method")
