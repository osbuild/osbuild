import abc
import contextlib
import os
import json
import tempfile
import concurrent.futures
from abc import abstractmethod
from typing import Dict, Tuple, Any, Iterable

from . import host
from .objectstore import ObjectStore
from .util.types import PathLike
from .util.jsoncomm import FdSet


class Source:
    """
    A single source with is corresponding options.
    """

    def __init__(self, info: Any, items: Dict[str, Any], options: Dict[str, Any]) -> None:
        self.info = info
        self.items = items or {}
        self.options = options

    def download(self, mgr: host.ServiceManager, store: ObjectStore, libdir: PathLike) -> Any:
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
    def make_items_file(self, tmp: str) -> Iterable[int]:
        with tempfile.TemporaryFile("w+", dir=tmp, encoding="utf-8") as f:
            json.dump(self.items, f)
            f.seek(0)
            yield f.fileno()


class SourceService(host.Service):
    """Source host service"""

    max_workers = 1

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.cache = None
        self.options = None
        self.tmpdir = None

    @abc.abstractmethod
    def fetch_one(self, checksum: str, desc: str) -> None:
        """Performs the actual fetch of an element described by its checksum and its descriptor"""

    def exists(self, checksum: str, _desc: str) -> bool:
        """Returns True if the item to download is in cache. """
        return os.path.isfile(f"{self.cache}/{checksum}")

    # pylint: disable=[no-self-use]
    def transform(self, checksum: str, desc: str) -> Tuple:
        """Modify the input data before downloading. By default only transforms an item object to a Tupple."""
        return checksum, desc

    def download(self, items: Dict[str, Any]) -> None:
        filtered = filter(lambda i: not self.exists(i[0], i[1]), items.items())  # discards items already in cache
        transformed = map(lambda i: self.transform(i[0], i[1]), filtered)  # prepare each item to be downloaded

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for _ in executor.map(self.fetch_one, *zip(*transformed)):
                pass

    @property
    @classmethod
    @abstractmethod
    def content_type(cls) -> None:
        """The content type of the source."""

    @staticmethod
    def load_items(fds: FdSet) -> Any:
        with os.fdopen(fds.steal(0)) as f:
            items = json.load(f)
        return items

    def setup(self, args: Dict[str, Any]) -> None:
        self.cache = os.path.join(args["cache"], self.content_type)
        os.makedirs(self.cache, exist_ok=True)
        self.options = args["options"]

    def dispatch(self, method: str, args: Dict[str, Any], fds: FdSet) -> Tuple[None, None]:
        if method == "download":
            self.setup(args)
            with tempfile.TemporaryDirectory(prefix=".unverified-", dir=self.cache) as self.tmpdir:
                self.download(SourceService.load_items(fds))
                return None, None

        raise host.ProtocolError("Unknown method")
