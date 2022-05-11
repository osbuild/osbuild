import abc
import contextlib
import os
import json
import tempfile
import concurrent.futures
from abc import abstractmethod
from typing import Dict, Tuple, List
from enum import Enum

from . import host
from .objectstore import ObjectStore
from .util.types import PathLike


class SourceErrorKind(Enum):
    FAILED = 0
    BAD_INPUT = 1
    DOWNLOAD = 2
    CHECKSUM = 3
    STORAGE = 4


class SourceError(Exception):

    def __init__(self, kind: SourceErrorKind, message: str, source: str):
        self.kind = kind
        self.message = message
        self.source = source
        super().__init__(message)


class Source:
    """
    A single source with is corresponding options.
    """

    def __init__(self, info, items, options) -> None:
        self.info = info
        self.items = items or {}
        self.options = options

    @staticmethod
    def raise_error(obj: Dict, _fds: List = None):
        raise SourceError(SourceErrorKind(obj["kind"]), obj["message"], obj["source"])

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
            client.call_with_fds("download", args, [fd], on_signal=Source.raise_error)

    @contextlib.contextmanager
    def make_items_file(self, tmp):
        with tempfile.TemporaryFile("w+", dir=tmp, encoding="utf-8") as f:
            json.dump(self.items, f)
            f.seek(0)
            yield f.fileno()


class SourceService(host.Service):
    """Source host service"""

    max_workers = 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache = None
        self.options = None
        self.tmpdir = None

    def signal_error(self, err: SourceError):
        self.emit_signal({"kind": err.kind.value, "message": err.message, "source": err.source})

    @abc.abstractmethod
    def fetch_one(self, checksum, desc) -> None:
        """Performs the actual fetch of an element described by its checksum and its descriptor"""

    def exists(self, checksum, _desc) -> bool:
        """Returns True if the item to download is in cache. """
        return os.path.isfile(f"{self.cache}/{checksum}")

    # pylint: disable=[no-self-use]
    def transform(self, checksum, desc) -> Tuple:
        """Modify the input data before downloading. By default only transforms an item object to a Tupple."""
        return checksum, desc

    def download(self, items: Dict) -> None:
        items = filter(lambda i: not self.exists(i[0], i[1]), items.items())  # discards items already in cache
        items = map(lambda i: self.transform(i[0], i[1]), items)  # prepare each item to be downloaded
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for _ in executor.map(self.fetch_one, *zip(*items)):
                pass

    @property
    @classmethod
    @abstractmethod
    def content_type(cls):
        """The content type of the source."""

    @staticmethod
    def load_items(fds):
        with os.fdopen(fds.steal(0)) as f:
            items = json.load(f)
        return items

    def setup(self, args):
        self.cache = os.path.join(args["cache"], self.content_type)
        os.makedirs(self.cache, exist_ok=True)
        self.options = args["options"]

    def dispatch(self, method: str, args, fds):
        if method == "download":
            self.setup(args)
            with tempfile.TemporaryDirectory(prefix=".unverified-", dir=self.cache) as self.tmpdir:
                return self.download(SourceService.load_items(fds)), None

        raise host.ProtocolError("Unknown method")
