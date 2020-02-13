
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
    def __init__(self, store: "ObjectStore", path: str):
        self.store = store
        os.makedirs(path, mode=0o755, exist_ok=True)
        self.path = path

    def init(self, source: str) -> None:
        """Initialize the object with source content"""
        subprocess.run(["cp", "--reflink=auto", "-a",
                        f"{source}/.", self.path],
                       check=True)

    @property
    def treesum(self) -> str:
        """Calculate the treesum of the object"""
        with self.open() as fd:
            m = hashlib.sha256()
            treesum.treesum(m, fd)
            treesum_hash = m.hexdigest()
            return treesum_hash

    @contextlib.contextmanager
    def open(self):
        """Open the directory and return the file descriptor"""
        try:
            fd = os.open(self.path, os.O_DIRECTORY)
            yield fd
        finally:
            os.close(fd)

    def move(self, destination: str):
        """Move the object to destination

        Does so atomically by using rename(2). If the
        target already exist, use that instead
        """
        with suppress_oserror(errno.ENOTEMPTY, errno.EEXIST):
            os.rename(self.path, destination)
        self.path = destination


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
                subprocess.run(["mount", "-o", "bind,ro,mode=0755", path, tmp], check=True)
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

        with self.tempdir() as tmp:
            # the object that is yielded will be added to the content store
            # on success as object_id
            obj = Object(self, f"{tmp}/tree")

            if base_id:
                # the base, the working tree and the output dir are all
                # on the same fs, so attempt a lightweight copy if the
                # fs supports it
                obj.init(self.resolve_ref(base_id))

            yield obj

            # if the yield above raises an exception, the working tree
            # is cleaned up by tempfile, otherwise, the it the content
            # of it was created or modified by the caller. All that is
            # left to do is to commit it to the object store
            self.commit(obj, object_id)

    def snapshot(self, object_path: str, object_id: str) -> str:
        """Commit `object_path` to store and ref it as `object_id`

        Create a snapshot of `object_path` and store it via its
        content hash in the object directory; additionally
        create a new reference to it via `object_id` in the
        reference directory.

        Returns: The treesum of the snapshot
        """
        # Make a new temporary directory and Object; initialize
        # the latter with the contents of `object_path` and commit
        # it to the store
        with self.tempdir() as tmp:
            obj = Object(self, f"{tmp}/tree")
            obj.init(object_path)
            return self.commit(obj, object_id)

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
        obj.move(f"{self.objects}/{treesum_hash}")

        # symlink the object_id (config hash) in the refs directory to the
        # treesum (content hash) in the objects directory. If a symlink by
        # that name alreday exists, atomically replace it, but leave the
        # backing object in place (it may be in use).
        with self.tempdir() as tmp:
            link = f"{tmp}/link"
            os.symlink(f"../objects/{treesum_hash}", link)
            os.replace(link, self.resolve_ref(object_id))

        return treesum_hash
