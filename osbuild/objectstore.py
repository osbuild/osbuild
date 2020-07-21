import contextlib
import errno
import hashlib
import os
import subprocess
import tempfile
import weakref
from typing import Optional

from osbuild.util import ctx, rmrf
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
        self.store = store
        self.reset()

    def init(self) -> None:
        """Initialize the object with content of its base"""
        self._check_writable()
        self._check_readers()
        self._check_writer()
        if self._init:
            return

        source = self.store.resolve_ref(self._base)
        subprocess.run(["cp", "--reflink=auto", "-a",
                        f"{source}/.", self._tree],
                       check=True)
        self._init = True

    @property
    def base(self) -> Optional[str]:
        return self._base

    @base.setter
    def base(self, base_id: Optional[str]):
        self._init = not base_id
        self._base = base_id

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

    def export(self, to_directory):
        """Copy object into an external directory"""
        with self.read() as from_directory:
            subprocess.run(
                [
                    "cp",
                    "--reflink=auto",
                    "-a",
                    f"{from_directory}/.",
                    to_directory,
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
    def __init__(self, store):
        self.store = store
        self.objects = f"{store}/objects"
        self.refs = f"{store}/refs"
        self.tmp = f"{store}/tmp"
        os.makedirs(self.store, exist_ok=True)
        os.makedirs(self.objects, exist_ok=True)
        os.makedirs(self.refs, exist_ok=True)
        os.makedirs(self.tmp, exist_ok=True)
        self._objs = weakref.WeakSet()

    def contains(self, object_id):
        if not object_id:
            return False
        return os.access(self.resolve_ref(object_id), os.F_OK)

    def resolve_ref(self, object_id: Optional[str]) -> Optional[str]:
        """Returns the path to the given object_id"""
        if not object_id:
            return None
        return f"{self.refs}/{object_id}"

    def tempdir(self, prefix=None, suffix=None):
        """Return a tempfile.TemporaryDirectory within the store"""
        return tempfile.TemporaryDirectory(dir=self.tmp,
                                           prefix=prefix,
                                           suffix=suffix)

    @contextlib.contextmanager
    def get(self, object_id):
        with Object(self) as obj:
            obj.base = object_id
            with obj.read() as path:
                yield path

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
        obj.store_tree(f"{self.objects}/{treesum_hash}")

        # symlink the object_id (config hash) in the refs directory to the
        # treesum (content hash) in the objects directory. If a symlink by
        # that name alreday exists, atomically replace it, but leave the
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
