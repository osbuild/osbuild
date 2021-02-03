import contextlib
import errno
import hashlib
import os
import subprocess
import tempfile
from typing import Optional

from osbuild.util.types import PathLike
from osbuild.util import ctx, jsoncomm, rmrf
from . import api
from . import treesum


__all__ = [
    "ObjectStore",
]


def mount(source, target, bind=True, ro=True, private=True, mode="0755"):
    options = []
    if bind:
        options += ["bind"]
    if ro:
        options += ["ro"]
    if mode:
        options += [mode]

    args = []
    if private:
        args += ["--make-private"]
    if options:
        args += ["-o", ",".join(options)]
    subprocess.run(["mount"] + args + [source, target], check=True)


def umount(target, lazy=True):
    args = []
    if lazy:
        args += ["--lazy"]
    subprocess.run(["umount"] + args + [target], check=True)


class Object:
    def __init__(self, store: "ObjectStore"):
        self._init = True
        self._readers = 0
        self._writer = False
        self._base = None
        self._workdir = None
        self._tree = None
        self.id = None
        self.store = store
        self.reset()

    def init(self) -> None:
        """Initialize the object with content of its base"""
        self._check_writable()
        self._check_readers()
        self._check_writer()
        if self._init:
            return

        with self.store.new(self._base) as obj:
            obj.export(self._tree)
        self._init = True

    @property
    def base(self) -> Optional[str]:
        return self._base

    @base.setter
    def base(self, base_id: Optional[str]):
        self._init = not base_id
        self._base = base_id
        self.id = base_id

    @property
    def treesum(self) -> str:
        """Calculate the treesum of the object"""
        with self._open() as fd:
            m = hashlib.sha256()
            treesum.treesum(m, fd)
            treesum_hash = m.hexdigest()
            return treesum_hash

    @property
    def _path(self) -> str:
        if self._base and not self._init:
            path = self.store.resolve_ref(self._base)
        else:
            path = self._tree
        return path

    @contextlib.contextmanager
    def write(self) -> str:
        """Return a path that can be written to"""
        self._check_writable()
        self._check_readers()
        self._check_writer()
        self.init()
        self.id = None
        with self.tempdir("writer") as target:
            mount(self._path, target, ro=False)
            try:
                self._writer = True
                yield target
            finally:
                umount(target)
                self._writer = False

    @contextlib.contextmanager
    def read(self) -> str:
        self._check_writable()
        self._check_writer()
        with self.tempdir("reader") as target:
            mount(self._path, target)
            try:
                self._readers += 1
                yield target
            finally:
                umount(target)
                self._readers -= 1

    def store_tree(self, destination: str):
        """Store the tree at destination and reset itself

        Moves the tree atomically by using rename(2). If the
        target already exist, does nothing. Afterwards it
        resets itself and can be used as if it was new.
        """
        self._check_writable()
        self._check_readers()
        self._check_writer()
        self.init()
        with ctx.suppress_oserror(errno.ENOTEMPTY, errno.EEXIST):
            os.rename(self._tree, destination)
        self.reset()

    def reset(self):
        self.cleanup()
        self._workdir = self.store.tempdir(suffix="object")
        self._tree = os.path.join(self._workdir.name, "tree")
        os.makedirs(self._tree, mode=0o755, exist_ok=True)
        self._init = not self._base

    def cleanup(self):
        self._check_readers()
        self._check_writer()
        if self._tree:
            # manually remove the tree, it might contain
            # files with immutable flag set, which will
            # throw off standard Python 3 tempdir cleanup
            rmrf.rmtree(self._tree)
            self._tree = None
        if self._workdir:
            self._workdir.cleanup()
            self._workdir = None
        self.id = None

    def _check_readers(self):
        """Internal: Raise a ValueError if there are readers"""
        if self._readers:
            raise ValueError("Read operation is ongoing")

    def _check_writable(self):
        """Internal: Raise a ValueError if not writable"""
        if not self._workdir:
            raise ValueError("Object is not writable")

    def _check_writer(self):
        """Internal: Raise a ValueError if there is a writer"""
        if self._writer:
            raise ValueError("Write operation is ongoing")

    @contextlib.contextmanager
    def _open(self):
        """Open the directory and return the file descriptor"""
        with self.read() as path:
            fd = os.open(path, os.O_DIRECTORY)
            try:
                yield fd
            finally:
                os.close(fd)

    def tempdir(self, suffix=None):
        workdir = self._workdir.name
        if suffix:
            suffix = "-" + suffix
        return tempfile.TemporaryDirectory(dir=workdir,
                                           suffix=suffix)

    def __enter__(self):
        self._check_writable()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def export(self, to_directory: PathLike):
        """Copy object into an external directory"""
        with self.read() as from_directory:
            subprocess.run(
                [
                    "cp",
                    "--reflink=auto",
                    "-a",
                    os.fspath(from_directory) + "/.",
                    os.fspath(to_directory),
                ],
                check=True,
            )


class HostTree:
    """Read-only access to the host file system

    An object that provides the same interface as
    `objectstore.Object` that can be used to read
    the host file-system.
    """
    def __init__(self, store):
        self.store = store

    @staticmethod
    def write():
        raise ValueError("Cannot write to host")

    @contextlib.contextmanager
    def read(self):
        with self.store.tempdir() as tmp:
            mount("/", tmp)
            try:
                yield tmp
            finally:
                umount(tmp)

    def cleanup(self):
        pass  # noop for the host


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
        self._objs = set()

    def _get_floating(self, object_id: str) -> Optional[Object]:
        """Internal: get a non-committed object"""
        for obj in self._objs:
            if obj.id == object_id:
                return obj
        return None

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

        obj = self.new(base_id=object_id)
        return obj

    def new(self, base_id=None):
        """Creates a new temporary `Object`.

        It returns a temporary instance of `Object`, the base
        optionally set to `base_id`. It can be used to interact
        with the store.
        If changes to the object's content were made (by calling
        `Object.write`), these must manually be committed to the
        store via `commit()`.
        """

        obj = Object(self)

        if base_id:
            # if we were given a base id then this is the base
            # content for the new object
            # NB: `Object` has copy-on-write semantics, so no
            # copying of the data takes places at this point
            obj.base = base_id

        self._objs.add(obj)

        return obj

    def commit(self, obj: Object, object_id: str) -> str:
        """Commits a Object to the object store

        Move the contents of the obj (Object) to object directory
        of the store with the content hash (obj.treesum) as its name.
        Creates a symlink to that ('objects/{hash}') in the references
        directory with the object_id as the name ('refs/{object_id}).
        If the link already exists, it will be atomically replaced.

        Returns: The treesum of the object
        """
        treesum_hash = obj.treesum

        # the object is stored in the objects directory using its content
        # hash as its name, ideally a given object_id (i.e., given config)
        # will always produce the same content hash, but that is not
        # guaranteed. If an object with the same treesum already exist, us
        # the existing one instead
        obj.store_tree(os.path.join(self.objects, treesum_hash))

        # symlink the object_id (config hash) in the refs directory to the
        # treesum (content hash) in the objects directory. If a symlink by
        # that name already exists, atomically replace it, but leave the
        # backing object in place (it may be in use).
        with self.tempdir() as tmp:
            link = f"{tmp}/link"
            os.symlink(f"../objects/{treesum_hash}", link)
            os.replace(link, self.resolve_ref(object_id))

        # the reference that is pointing to `treesum_hash` is now the base
        # of `obj`. It is not actively initialized but any subsequent calls
        # to `obj.write()` will initialize it again
        # NB: in the case that an object with the same treesum as `obj`
        # already existed in the store obj.store_tree() will not actually
        # have written anything to the store. In this case `obj` will then
        # be initialized with the content of the already existing object.
        obj.base = object_id

        return treesum_hash

    def cleanup(self):
        """Cleanup all created Objects that are still alive"""
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

        reader = obj.read()
        path = self._stack.enter_context(reader)
        sock.send({"path": path})

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

    def source(self, name: str) -> str:
        msg = {
            "method": "source",
            "name": name
        }

        self.client.send(msg)
        msg, _, _ = self.client.recv()

        return msg["path"]
