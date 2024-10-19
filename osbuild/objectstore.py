import contextlib
import enum
import json
import os
import subprocess
import tempfile
import time
from typing import Any, Optional, Set, Union

from osbuild.util import jsoncomm
from osbuild.util.fscache import FsCache, FsCacheInfo
from osbuild.util.mnt import mount, umount
from osbuild.util.path import clamp_mtime
from osbuild.util.types import PathLike

from . import api

__all__ = [
    "ObjectStore",
]


class PathAdapter:
    """Expose an object attribute as `os.PathLike`"""

    def __init__(self, obj: Any, attr: str) -> None:
        self.obj = obj
        self.attr = attr

    def __fspath__(self):
        return getattr(self.obj, self.attr)


class Object:
    class Mode(enum.Enum):
        READ = 0
        WRITE = 1

    class Metadata:
        """store and retrieve metadata for an object"""

        def __init__(self, base, folder: Optional[str] = None) -> None:
            self.base = base
            self.folder = folder
            os.makedirs(self.path, exist_ok=True)

        def _path_for_key(self, key) -> str:
            assert key
            name = f"{key}.json"
            return os.path.join(self.path, name)

        @property
        def path(self):
            if not self.folder:
                return self.base
            return os.path.join(self.base, self.folder)

        @contextlib.contextmanager
        def write(self, key):

            tmp = tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf8",
                dir=self.path,
                prefix=".",
                suffix=".tmp.json",
                delete=True,
            )

            with tmp as f:
                yield f

                f.flush()

                # if nothing was written to the file
                si = os.stat(tmp.name)
                if si.st_size == 0:
                    return

                dest = self._path_for_key(key)
                # ensure it is proper json?
                os.link(tmp.name, dest)

        @contextlib.contextmanager
        def read(self, key):
            dest = self._path_for_key(key)
            try:
                with open(dest, "r", encoding="utf8") as f:
                    yield f
            except FileNotFoundError:
                raise KeyError(f"No metadata for '{key}'") from None

        def set(self, key: str, data):

            if data is None:
                return

            with self.write(key) as f:
                json.dump(data, f, indent=2)

        def get(self, key: str):
            with contextlib.suppress(KeyError):
                with self.read(key) as f:
                    return json.load(f)
            return None

        def __fspath__(self):
            return self.path

    def __init__(self, cache: FsCache, uid: str, mode: Mode):
        self._cache = cache
        self._mode = mode
        self._id = uid
        self._path = None
        self._meta: Optional[Object.Metadata] = None
        self._stack: Optional[contextlib.ExitStack] = None
        self.source_epoch = None  # see finalize()

    def _open_for_reading(self):
        name = self._stack.enter_context(
            self._cache.load(self.id)
        )
        self._path = os.path.join(self._cache, name)

    def _open_for_writing(self):
        name = self._stack.enter_context(
            self._cache.stage()
        )
        self._path = os.path.join(self._cache, name)
        os.makedirs(os.path.join(self._path, "tree"))

    def __enter__(self):
        assert not self.active
        self._stack = contextlib.ExitStack()
        if self.mode == Object.Mode.READ:
            self._open_for_reading()
        else:
            self._open_for_writing()

        # Expose our base path as `os.PathLike` via `PathAdater`
        # so any changes to it, e.g. via `store_tree`, will be
        # automatically picked up by `Metadata`.
        wrapped = PathAdapter(self, "_path")
        self._meta = self.Metadata(wrapped, folder="meta")

        if self.mode == Object.Mode.WRITE:
            self.meta.set("info", {
                "created": int(time.time()),
            })

        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        assert self.active
        self.cleanup()

    @property
    def active(self) -> bool:
        return self._stack is not None

    @property
    def id(self) -> Optional[str]:
        return self._id

    @property
    def mode(self) -> Mode:
        return self._mode

    def init(self, base: "Object"):
        """Initialize the object with the base object"""
        self._check_mode(Object.Mode.WRITE)
        assert self.active
        assert self._path

        subprocess.run(
            [
                "cp",
                "--reflink=auto",
                "-a",
                os.fspath(base.path) + "/.",
                os.fspath(self.path),
            ],
            check=True,
        )

    @property
    def path(self) -> str:
        assert self.active
        assert self._path
        return self._path

    @property
    def tree(self) -> str:
        return os.path.join(self.path, "tree")

    @property
    def meta(self) -> Metadata:
        assert self.active
        assert self._meta
        return self._meta

    @property
    def created(self) -> int:
        """When was the object created

        It is stored as `created` in the `info` metadata entry,
        and thus will also get overwritten if the metadata gets
        overwritten via `init()`.
        NB: only valid to access when the object is active.
        """
        info = self.meta.get("info")
        assert info, "info metadata missing"
        return info["created"]

    def clamp_mtime(self):
        """Clamp mtime of files and dirs to source_epoch

        If a source epoch is specified we clamp all files that
        are newer then our own creation timestap to the given
        source epoch. As a result all files created during the
        build should receive the source epoch modification time
        """
        if self.source_epoch is None:
            return

        clamp_mtime(self.tree, self.created, self.source_epoch)

    def finalize(self):
        if self.mode != Object.Mode.WRITE:
            return

        self.clamp_mtime()

        # put the object into the READER state
        self._mode = Object.Mode.READ

    def cleanup(self):
        if self._stack:
            self._stack.close()
            self._stack = None

    def _check_mode(self, want: Mode):
        """Internal: Raise a ValueError if we are not in the desired mode"""
        if self.mode != want:
            raise ValueError(f"Wrong object mode: {self.mode}, want {want}")

    def export(self, to_directory: PathLike, skip_preserve_owner=False):
        """Copy object into an external directory"""
        cp_cmd = [
            "cp",
            "--reflink=auto",
            "-a",
        ]
        if skip_preserve_owner:
            cp_cmd += ["--no-preserve=ownership"]
        cp_cmd += [
            os.fspath(self.tree) + "/.",
            os.fspath(to_directory),
        ]
        subprocess.run(cp_cmd, check=True)

    def __fspath__(self):
        return self.tree


class HostTree:
    """Read-only access to the host file system

    An object that provides the same interface as
    `objectstore.Object` that can be used to read
    the host file-system.
    """

    _root: Optional[tempfile.TemporaryDirectory]

    def __init__(self, store):
        self.store = store
        self._root = None
        self.init()

    def init(self):
        if self._root:
            return

        self._root = self.store.tempdir(prefix="host")

        root = self._root.name
        # Create a bare bones root file system. Starting with just
        # /usr mounted from the host.
        usr = os.path.join(root, "usr")
        os.makedirs(usr)
        # Also add in /etc/containers, which will allow us to access
        # /etc/containers/policy.json and enable moving containers
        # (skopeo): https://github.com/osbuild/osbuild/pull/1410
        # If https://github.com/containers/image/issues/2157 ever gets
        # fixed we can probably remove this bind mount.
        etc_containers = os.path.join(root, "etc", "containers")
        os.makedirs(etc_containers)

        # ensure / is read-only
        mount(root, root)
        mount("/usr", usr)
        mount("/etc/containers", etc_containers)

    @property
    def tree(self) -> os.PathLike:
        if not self._root:
            raise AssertionError("HostTree not initialized")
        return self._root.name

    def cleanup(self):
        if self._root:
            umount(self._root.name)
            self._root.cleanup()
            self._root = None

    def __fspath__(self) -> os.PathLike:
        return self.tree


class ContainerMountTree:
    """Access to a container based root filesystem.

    An object that provides a similar interface to
    `objectstore.Object` and provides access to a container
    """

    def __init__(self, from_container: str) -> None:
        self._from_container = ""
        self._root = ""
        self.init(from_container)

    def init(self, from_container: str) -> None:
        self._from_container = from_container
        result = subprocess.run(
            ["podman", "image", "mount", from_container],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            check=False,
        )
        if result.returncode != 0:
            code = result.returncode
            msg = result.stderr.strip()
            raise RuntimeError(f"Failed to mount image ({code}): {msg}")
        self._root = result.stdout.strip()

    @property
    def tree(self) -> str:
        if not self._root:
            raise AssertionError(f"ContainerMountTree for {self._from_container} not initialized")
        return self._root

    def cleanup(self):
        if self._root:
            subprocess.run(
                ["podman", "image", "umount", self._from_container],
                stdout=subprocess.DEVNULL,
                check=True,
            )
            self._root = ""

    def __fspath__(self) -> str:
        return self.tree


class ObjectStore(contextlib.AbstractContextManager):
    def __init__(self, store: PathLike):
        self.cache = FsCache("osbuild", store)
        self.tmp = os.path.join(store, "tmp")
        os.makedirs(self.store, exist_ok=True)
        os.makedirs(self.objects, exist_ok=True)
        os.makedirs(self.tmp, exist_ok=True)
        self._objs: Set[Object] = set()
        self._host_tree: Optional[HostTree] = None
        self._stack = contextlib.ExitStack()

    def _get_floating(self, object_id: str) -> Optional[Object]:
        """Internal: get a non-committed object"""
        for obj in self._objs:
            if obj.mode == Object.Mode.READ and obj.id == object_id:
                return obj
        return None

    @property
    def maximum_size(self) -> Optional[Union[int, str]]:
        info = self.cache.info
        return info.maximum_size

    @maximum_size.setter
    def maximum_size(self, size: Union[int, str]):
        info = FsCacheInfo(maximum_size=size)
        self.cache.info = info

    @property
    def active(self) -> bool:
        # pylint: disable=protected-access
        return self.cache._is_active()

    @property
    def store(self):
        return os.fspath(self.cache)

    @property
    def objects(self):
        return os.path.join(self.cache, "objects")

    @property
    def host_tree(self) -> HostTree:
        assert self.active

        if not self._host_tree:
            self._host_tree = HostTree(self)
        return self._host_tree

    def contains(self, object_id):
        if not object_id:
            return False

        if self._get_floating(object_id):
            return True

        try:
            with self.cache.load(object_id):
                return True
        except FsCache.MissError:
            return False

    def tempdir(self, prefix=None, suffix=None):
        """Return a tempfile.TemporaryDirectory within the store"""
        return tempfile.TemporaryDirectory(dir=self.tmp,
                                           prefix=prefix,
                                           suffix=suffix)

    def get(self, object_id):
        assert self.active

        obj = self._get_floating(object_id)
        if obj:
            return obj

        try:
            obj = Object(self.cache, object_id, Object.Mode.READ)
            self._stack.enter_context(obj)
            return obj
        except FsCache.MissError:
            return None

    def new(self, object_id: str):
        """Creates a new `Object` and open it for writing.

        It returns a instance of `Object` that can be used to
        write tree and metadata. Use `commit` to attempt to
        store the object in the cache.
        """
        assert self.active

        obj = Object(self.cache, object_id, Object.Mode.WRITE)
        self._stack.enter_context(obj)

        self._objs.add(obj)

        return obj

    def commit(self, obj: Object, object_id: str):
        """Commits the Object to the object cache as `object_id`.

        Attempts to store the contents of `obj` and its metadata
        in the object cache. Whether anything is actually stored
        depends on the configuration of the cache, i.e. its size
        and how much free space is left or can be made available.
        Therefore the caller should not assume that the stored
        object can be retrived at all.
        """

        assert self.active

        # we clamp the mtime of `obj` itself so that it
        # resuming a snapshop and building with a snapshot
        # goes through the same code path
        obj.clamp_mtime()

        self.cache.store_tree(object_id, obj.path + "/.")

    def cleanup(self):
        """Cleanup all created Objects that are still alive"""
        if self._host_tree:
            self._host_tree.cleanup()
            self._host_tree = None

        self._stack.close()
        self._objs = set()

    def __fspath__(self):
        return os.fspath(self.store)

    def __enter__(self):
        assert not self.active
        self._stack.enter_context(self.cache)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        assert self.active
        self.cleanup()


class StoreServer(api.BaseAPI):

    endpoint = "store"

    def __init__(self, store: ObjectStore, *, socket_address=None):
        super().__init__(socket_address)
        self.store = store
        self.tmproot = store.tempdir(prefix="store-server-")
        self._stack = contextlib.ExitStack()

    def _cleanup(self):
        self.tmproot.cleanup()
        self.tmproot = None
        self._stack.close()
        self._stack = None

    def _read_tree(self, msg, sock):
        object_id = msg["object-id"]
        obj = self.store.get(object_id)
        if not obj:
            sock.send({"path": None})
            return

        sock.send({"path": obj.tree})

    def _read_tree_at(self, msg, sock):
        object_id = msg["object-id"]
        target = msg["target"]
        subtree = msg["subtree"]

        obj = self.store.get(object_id)
        if not obj:
            sock.send({"path": None})
            return

        try:
            source = os.path.join(obj, subtree.lstrip("/"))
            mount(source, target)
            self._stack.callback(umount, target)

        # pylint: disable=broad-except
        except Exception as e:
            sock.send({"error": str(e)})
            return

        sock.send({"path": target})

    def _mkdtemp(self, msg, sock):
        args = {
            "suffix": msg.get("suffix"),
            "prefix": msg.get("prefix"),
            "dir": self.tmproot.name
        }

        path = tempfile.mkdtemp(**args)
        sock.send({"path": path})

    def _source(self, msg, sock):
        name = msg["name"]
        base = self.store.store
        path = os.path.join(base, "sources", name)
        sock.send({"path": path})

    def _message(self, msg, _fds, sock):
        if msg["method"] == "read-tree":
            self._read_tree(msg, sock)
        elif msg["method"] == "read-tree-at":
            self._read_tree_at(msg, sock)
        elif msg["method"] == "mkdtemp":
            self._mkdtemp(msg, sock)
        elif msg["method"] == "source":
            self._source(msg, sock)
        else:
            raise ValueError("Invalid RPC call", msg)


class StoreClient:
    def __init__(self, connect_to="/run/osbuild/api/store"):
        self.client = jsoncomm.Socket.new_client(connect_to)

    def __del__(self):
        if self.client is not None:
            self.client.close()

    def mkdtemp(self, suffix=None, prefix=None):
        msg = {
            "method": "mkdtemp",
            "suffix": suffix,
            "prefix": prefix
        }

        self.client.send(msg)
        msg, _, _ = self.client.recv()

        return msg["path"]

    def read_tree(self, object_id: str):
        msg = {
            "method": "read-tree",
            "object-id": object_id
        }

        self.client.send(msg)
        msg, _, _ = self.client.recv()

        return msg["path"]

    def read_tree_at(self, object_id: str, target: str, path="/"):
        msg = {
            "method": "read-tree-at",
            "object-id": object_id,
            "target": os.fspath(target),
            "subtree": os.fspath(path)
        }

        self.client.send(msg)
        msg, _, _ = self.client.recv()

        err = msg.get("error")
        if err:
            raise RuntimeError(err)

        return msg["path"]

    def source(self, name: str) -> str:
        msg = {
            "method": "source",
            "name": name
        }

        self.client.send(msg)
        msg, _, _ = self.client.recv()

        return msg["path"]
