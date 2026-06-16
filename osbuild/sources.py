import abc
import hashlib
import json
import os
import shutil
import tempfile
from typing import ClassVar, Dict

from . import host
from .objectstore import ObjectStore


class SourceItemResult:
    def __init__(self, success=True, metadata=None, error=""):
        self.success = success
        self.metadata = metadata if metadata is not None else {}
        self.error = error

    def set_error(self, error):
        self.error = error
        self.success = False

    def as_dict(self):
        return {
            "success": self.success,
            "metadata": self.metadata,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data):
        r = cls(data["success"])
        r.metadata = data.get("metadata", {})
        r.error = data.get("error", "")
        return r


class SourceResults:
    """Contains the results of a single source type.

    Because this is passed to monitor.BaseMonitor.result, the name, id,
    success and output properties need to be present.
    """

    def __init__(self, source_type):
        self.source_type = source_type
        self.success = True
        self.results = []

    def add(self, result: SourceItemResult):
        self.results.append(result)
        if not result.success:
            self.success = False

    @property
    def id(self):
        return self.source_type

    @property
    def name(self):
        return f"source {self.source_type}"

    @property
    def output(self):
        if self.success:
            return f"source {self.source_type} finished successfully"
        error = self.results[-1].error
        return f"source {self.source_type} finished unsuccessfully: {error}"

    def as_dict(self):
        return {
            "name": self.name,
            "source_type": self.source_type,
            "success": self.success,
            "output": self.output,
            "results": [r.as_dict() for r in self.results],
        }

    @classmethod
    def from_dict(cls, data):
        sr = cls(data["source_type"])
        sr.success = data["success"]
        sr.results = [SourceItemResult.from_dict(r) for r in data["results"]]
        return sr


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

    def download(self, mgr: host.ServiceManager, store: ObjectStore) -> SourceResults:
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
        return SourceResults.from_dict(reply)

    def copy(self, mgr: host.ServiceManager, store: ObjectStore, dst_store: ObjectStore) -> SourceResults:
        source = self.info_name
        cache = os.path.join(store.store, "sources")
        dst_cache = os.path.join(dst_store.store, "sources")

        args = {
            "items": self.items,
            "options": self.options,
            "cache": cache,
            "dst_cache": dst_cache,
        }

        client = mgr.start(f"source/{source}", self.info_path)
        reply = client.call("copy", args)
        return SourceResults.from_dict(reply)

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
    def fetch_one(self, checksum, desc) -> SourceItemResult:
        """Performs the actual fetch of an element described by its checksum and its descriptor"""

    @abc.abstractmethod
    def fetch_all(self, items: Dict) -> Dict:
        """Fetch all sources."""

    def exists(self, checksum, _desc) -> bool:
        """Returns True if the item to download is in cache. """
        return os.path.isfile(f"{self.cache}/{checksum}")

    def copy_all(self, items: Dict, dst_cache: str) -> Dict:
        """Copies the source to the destination"""
        target_dir = os.path.join(dst_cache, self.content_type)
        os.makedirs(target_dir, exist_ok=True)
        results = SourceResults(self.id)
        for item in items:
            res = SourceItemResult(metadata={
                "checksum": item,
            })
            try:
                shutil.copy2(os.path.join(self.cache, item), os.path.join(target_dir, item))
            except Exception as e:  # pylint: disable=broad-exception-caught
                res.set_error(str(e))
            results.add(res)
        return results.as_dict()

    def setup(self, args):
        self.cache = os.path.join(args["cache"], self.content_type)
        os.makedirs(self.cache, exist_ok=True)
        self.options = args["options"]

    def dispatch(self, method: str, args, fds):
        if method == "download":
            self.setup(args)
            with tempfile.TemporaryDirectory(prefix=".unverified-", dir=self.cache) as self.tmpdir:
                sourceresults = self.fetch_all(args["items"])
                return sourceresults, None

        elif method == "copy":
            self.setup(args)
            sourceresults = self.copy_all(args["items"], args["dst_cache"])
            return sourceresults, None

        raise host.ProtocolError("Unknown method")
