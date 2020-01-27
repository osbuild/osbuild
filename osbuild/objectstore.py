
import contextlib
import errno
import hashlib
import os
import subprocess
import tempfile
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


class TreeObject:
    def __init__(self, path: str):
        os.makedirs(path, mode=0o755, exist_ok=True)
        self.path = path

    def init(self, source: str) -> None:
        """Initialize the tree with a source tree"""
        subprocess.run(["cp", "--reflink=auto", "-a",
                        f"{source}/.", self.path],
                       check=True)

    @property
    def treesum(self) -> str:
        """Calculate the treesum of the tree"""
        fd = os.open(self.path, os.O_DIRECTORY)
        try:
            m = hashlib.sha256()
            treesum.treesum(m, fd)
            treesum_hash = m.hexdigest()
        finally:
            os.close(fd)

        return treesum_hash


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
        return os.access(f"{self.refs}/{object_id}", os.F_OK)

    @contextlib.contextmanager
    def get(self, object_id):
        with tempfile.TemporaryDirectory(dir=self.store) as tmp:
            if object_id:
                subprocess.run(["mount", "-o", "bind,ro,mode=0755", f"{self.refs}/{object_id}", tmp], check=True)
                try:
                    yield tmp
                finally:
                    subprocess.run(["umount", "--lazy", tmp], check=True)
            else:
                # None was given as object_id, just return an empty directory
                yield tmp


    @contextlib.contextmanager
    def new(self, object_id, base_id=None):
        """Creates a new directory for `object_id`.

        This method must be used as a context manager. It returns a path to a
        temporary directory and only commits it when the context completes
        without raising an exception.
        """
        with tempfile.TemporaryDirectory(dir=self.store) as tmp:
            # the tree that is yielded will be added to the content store
            # on success as object_id
            tree = TreeObject(f"{tmp}/tree")

            if base_id:
                # the base, the working tree and the output tree are all on
                # the same fs, so attempt a lightweight copy if the fs
                # supports it
                tree.init(f"{self.refs}/{base_id}")

            yield tree.path

            # if the yield above raises an exception, the working tree
            # is cleaned up by tempfile, otherwise, the it the content
            # of it was created or modified by the caller. All that is
            # left to do is to commit it to the object store
            self.commit(tree, object_id)

    def snapshot(self, tree_path: str, object_id: str) -> str:
        """Commit `tree_path` to store and ref it as `object_id`

        Create a snapshot of `tree_path` and store it via its
        content hash in the object directory; additionally
        create a new reference to it via `object_id` in the
        reference directory.

        Returns: The treesum of the snapshot
        """
        # Make a new temporary directory and TreeObject; initialize
        # the latter with the contents of `tree_path` and commit
        # it to the store
        with tempfile.TemporaryDirectory(dir=self.store) as tmp:
            tree = TreeObject(f"{tmp}/tree")
            tree.init(tree_path)
            return self.commit(tree, object_id)

    def commit(self, tree: TreeObject, object_id: str) -> str:
        """Commits a TreeObject to the object store

        Move the contents of the tree (TreeObject) to object directory
        of the store with the content hash (tree.treesum) as its name.
        Creates a symlink to that ('objects/{hash}') in the references
        directory with the object_id as the name ('refs/{object_id}).
        If the link already exists, it will be atomically replaced.

        Returns: The treesum of the tree
        """
        treesum_hash = tree.treesum

        # the tree is stored in the objects directory using its content
        # hash as its name, ideally a given object_id (i.e., given config)
        # will always produce the same content hash, but that is not
        # guaranteed
        output_tree = f"{self.objects}/{treesum_hash}"

        # if a tree with the same treesum already exist, use that
        with suppress_oserror(errno.ENOTEMPTY, errno.EEXIST):
            os.rename(tree.path, output_tree)
        tree.path = output_tree

        # symlink the object_id (config hash) in the refs directory to the
        # treesum (content hash) in the objects directory. If a symlink by
        # that name alreday exists, atomically replace it, but leave the
        # backing object in place (it may be in use).
        with tempfile.TemporaryDirectory(dir=self.store) as tmp:
            link = f"{tmp}/link"
            os.symlink(f"../objects/{treesum_hash}", link)
            os.replace(link, f"{self.refs}/{object_id}")

        return treesum_hash
