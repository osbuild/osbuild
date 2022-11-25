import contextlib
import enum
import json
import os
import subprocess
import tempfile
import uuid
from typing import Any, Optional, Set

from osbuild.util import jsoncomm, rmrf
from osbuild.util.mnt import mount, umount
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

    def __init__(self, store: "ObjectStore", uid: str, mode: Mode):
        self._mode = mode
        self._workdir = None
        self._id = uid
        self.store = store

        if self.mode == Object.Mode.READ:
            path = self.store.resolve_ref(uid)
            assert path is not None
            self._path = os.path.join(path, "data")
        else:
            workdir = self.tempdir("workdir")
            self._workdir = workdir
            self._path = os.path.join(workdir.name, "data")
            tree = os.path.join(self._path, "tree")
            os.makedirs(tree)

        # Expose our base path as `os.PathLike` via `PathAdater`
        # so any changes to it, e.g. via `store_tree`, will be
        # automatically picked up by `Metadata`.
        wrapped = PathAdapter(self, "_path")
        self._meta = self.Metadata(wrapped, folder="meta")

    @property
    def id(self) -> Optional[str]:
        return self._id

    @property
    def mode(self) -> Mode:
        return self._mode

    def init(self, base: "Object"):
        """Initialize the object with the base object"""
        self._check_mode(Object.Mode.WRITE)
        base.clone(self._path)

    @property
    def tree(self) -> str:
        return os.path.join(self._path, "tree")

    @property
    def meta(self) -> Metadata:
        return self._meta

    def store_tree(self):
        """Store the tree with a fresh name and close it

        Moves the tree atomically by using rename(2), to a
        randomly generated unique name.

        This puts the object into the READ state.
        """
        self._check_mode(Object.Mode.WRITE)

        name = str(uuid.uuid4())

        base = os.path.join(self.store.objects, name)
        os.makedirs(base)
        destination = os.path.join(base, "data")
        os.rename(self._path, destination)
        self._path = destination

        self.finalize()
        self.cleanup()

        return name

    def finalize(self):
        if self.mode != Object.Mode.WRITE:
            return

        # put the object into the READER state
        self._mode = Object.Mode.READ

    def cleanup(self):
        workdir = self._workdir
        if workdir:
            # manually remove the tree, it might contain
            # files with immutable flag set, which will
            # throw off standard Python 3 tempdir cleanup
            rmrf.rmtree(os.path.join(workdir.name, "data"))

            workdir.cleanup()
            self._workdir = None

    def _check_mode(self, want: Mode):
        """Internal: Raise a ValueError if we are not in the desired mode"""
        if self.mode != want:
            raise ValueError(f"Wrong object mode: {self.mode}, want {want}")

    def tempdir(self, suffix=None):
        if suffix:
            suffix = "-" + suffix
        name = f"object-{self._id[:7]}-"
        return self.store.tempdir(prefix=name, suffix=suffix)

    def export(self, to_directory: PathLike):
        """Copy object into an external directory"""
        subprocess.run(
            [
                "cp",
                "--reflink=auto",
                "-a",
                os.fspath(self.tree) + "/.",
                os.fspath(to_directory),
            ],
            check=True,
        )

    def clone(self, to_directory: PathLike):
        """Clone the object to the specified directory"""

        assert self._path

        subprocess.run(
            [
                "cp",
                "--reflink=auto",
                "-a",
                os.fspath(self._path) + "/.",
                os.fspath(to_directory),
            ],
            check=True,
        )

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
        # Create a bare bones root file system
        # with just /usr mounted from the host
        usr = os.path.join(root, "usr")
        os.makedirs(usr)

        # ensure / is read-only
        mount(root, root)
        mount("/usr", usr)

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


class ObjectStore(contextlib.AbstractContextManager):
    def __init__(self, store: PathLike):
        self.store = store
        self.objects = os.path.join(store, "objects")
        self.refs = os.path.join(store, "refs")
        self.tmp = os.path.join(store, "tmp")
        os.makedirs(self.store, exist_ok=True)
        os.makedirs(self.objects, exist_ok=True)
        os.makedirs(self.refs, exist_ok=True)
        os.makedirs(self.tmp, exist_ok=True)
        self._objs: Set[Object] = set()
        self._host_tree: Optional[HostTree] = None

    def _get_floating(self, object_id: str) -> Optional[Object]:
        """Internal: get a non-committed object"""
        for obj in self._objs:
            if obj.mode == Object.Mode.READ and obj.id == object_id:
                return obj
        return None

    @property
    def host_tree(self) -> HostTree:
        if not self._host_tree:
            self._host_tree = HostTree(self)
        return self._host_tree

    def contains(self, object_id):
        if not object_id:
            return False

        if self._get_floating(object_id):
            return True

        return os.access(self.resolve_ref(object_id), os.F_OK)

    def resolve_ref(self, object_id: Optional[str]) -> Optional[str]:
        """Returns the path to the given object_id"""
        if not object_id:
            return None
        return os.path.join(self.refs, object_id)

    def tempdir(self, prefix=None, suffix=None):
        """Return a tempfile.TemporaryDirectory within the store"""
        return tempfile.TemporaryDirectory(dir=self.tmp,
                                           prefix=prefix,
                                           suffix=suffix)

    def get(self, object_id):
        obj = self._get_floating(object_id)
        if obj:
            return obj

        if not self.contains(object_id):
            return None

        return Object(self, object_id, Object.Mode.READ)

    def new(self, object_id: str):
        """Creates a new `Object` and open it for writing.

        It returns a temporary instance of `Object`, the base
        optionally set to `base_id`. It can be used to interact
        with the store.
        If changes to the object's content were made (by calling
        `Object.write`), these must manually be committed to the
        store via `commit()`.
        """

        obj = Object(self, object_id, Object.Mode.WRITE)

        self._objs.add(obj)

        return obj

    def commit(self, obj: Object, object_id: str) -> str:
        """Commits a Object to the object store

        Move the contents of the obj (Object) to object directory
        of the store with a universally unique name. Creates a
        symlink to that ('objects/{hash}') in the references
        directory with the object_id as the name ('refs/{object_id}).
        If the link already exists, it will be atomically replaced.

        If object_id is different from the id of the object, a copy
        of the object will be stored.

        Returns: The name of the object
        """

        # The supplied object_id is not the object's final id, so
        # we have to make a copy first
        if obj.id != object_id:
            tmp = self.new(object_id)
            tmp.init(obj)
            obj = tmp

        # The object is stored in the objects directory using its unique
        # name. This means that each commit will always result in a new
        # object in the store, even if an identical one exists.
        object_name = obj.store_tree()

        # symlink the object_id (config hash) in the refs directory to the
        # object name in the objects directory. If a symlink by that name
        # already exists, atomically replace it, but leave the backing object
        # in place (it may be in use).
        with self.tempdir() as tmp:
            link = f"{tmp}/link"
            os.symlink(f"../objects/{object_name}", link)

            ref = self.resolve_ref(object_id)

            if not ref:
                raise RuntimeError("commit with unresolvable ref")

            os.replace(link, ref)

        return object_name

    def cleanup(self):
        """Cleanup all created Objects that are still alive"""
        if self._host_tree:
            self._host_tree.cleanup()
            self._host_tree = None

        for obj in self._objs:
            obj.cleanup()

    def __exit__(self, exc_type, exc_val, exc_tb):
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
