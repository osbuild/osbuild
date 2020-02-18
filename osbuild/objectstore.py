
import contextlib
import errno
import hashlib
import os
import subprocess
import tempfile
from typing import Optional
from . import treesum


__all__ = [
    "ObjectStore",
]


@contextlib.contextmanager
def suppress_oserror(*errnos):
    """A context manager that suppresses any OSError with an errno in `errnos`.

    Like contextlib.suppress, but can differentiate between OSErrors.
    """
    try:
        yield
    except OSError as e:
        if e.errno not in errnos:
            raise e


class Object:
    def __init__(self, store: "ObjectStore"):
        self._init = True
        self._base = None
        self._workdir = None
        self._tree = None
        self.store = store
        self.reset()

    def init(self) -> None:
        """Initialize the object with content of its base"""
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

    def write(self) -> str:
        """Return a path that can be written to"""
        self.init()
        return self._tree

    def store_tree(self, destination: str):
        """Store the tree at destination and reset itself

        Moves the tree atomically by using rename(2). If the
        target already exist, does nothing. Afterwards it
        resets itself and can be used as if it was new.
        """
        self.init()
        with suppress_oserror(errno.ENOTEMPTY, errno.EEXIST):
            os.rename(self._tree, destination)
        self.reset()

    def reset(self):
        self.cleanup()
        self._workdir = self.store.tempdir(suffix="object")
        self._tree = os.path.join(self._workdir.name, "tree")
        os.makedirs(self._tree, mode=0o755, exist_ok=True)
        self._init = not self._base

    def cleanup(self):
        if self._workdir:
            self._workdir.cleanup()
            self._workdir = None

    @contextlib.contextmanager
    def _open(self):
        """Open the directory and return the file descriptor"""
        try:
            fd = os.open(self._path, os.O_DIRECTORY)
            yield fd
        finally:
            os.close(fd)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return exc_type is None


class ObjectStore:
    def __init__(self, store):
        self.store = store
        self.objects = f"{store}/objects"
        self.refs = f"{store}/refs"
        os.makedirs(self.store, exist_ok=True)
        os.makedirs(self.objects, exist_ok=True)
        os.makedirs(self.refs, exist_ok=True)

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
        return tempfile.TemporaryDirectory(dir=self.store,
                                           prefix=prefix,
                                           suffix=suffix)

    @contextlib.contextmanager
    def get(self, object_id):
        with self.tempdir() as tmp:
            if object_id:
                path = self.resolve_ref(object_id)
                subprocess.run(["mount", "--make-private", "-o", "bind,ro,mode=0755", path, tmp], check=True)
                try:
                    yield tmp
                finally:
                    subprocess.run(["umount", "--lazy", tmp], check=True)
            else:
                # None was given as object_id, just return an empty directory
                yield tmp


    @contextlib.contextmanager
    def new(self, object_id, base_id=None):
        """Creates a new `Object` for `object_id`.

        This method must be used as a context manager. It returns a new
        temporary instance of `Object`. It will only be committed to the
        store if the context completes without raising an exception.
        """

        with Object(self) as obj:
            # the object that is yielded will be added to the content store
            # on success as object_id

            if base_id:
                # if we were given a base id then this is the base for the
                # new object
                # NB: its initialization is deferred to the first write
                obj.base = base_id

            yield obj

            # if the yield above raises an exception, the working tree
            # is cleaned up by tempfile, otherwise, the it the content
            # of it was created or modified by the caller. All that is
            # left to do is to commit it to the object store
            self.commit(obj, object_id)

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
