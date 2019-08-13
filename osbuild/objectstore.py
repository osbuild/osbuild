
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


class ObjectStore:
    def __init__(self, store):
        self.store = store
        self.objects = f"{store}/objects"
        self.refs = f"{store}/refs"
        os.makedirs(self.store, exist_ok=True)
        os.makedirs(self.objects, exist_ok=True)
        os.makedirs(self.refs, exist_ok=True)

    def has_tree(self, tree_id):
        if not tree_id:
            return False
        return os.access(f"{self.refs}/{tree_id}", os.F_OK)

    @contextlib.contextmanager
    def get_tree(self, tree_id):
        with tempfile.TemporaryDirectory(dir=self.store) as tmp:
            if tree_id:
                subprocess.run(["mount", "-o", "bind,ro,mode=0755", f"{self.refs}/{tree_id}", tmp], check=True)
                try:
                    yield tmp
                finally:
                    subprocess.run(["umount", "--lazy", tmp], check=True)
            else:
                # None was given as tree_id, just return an empty directory
                yield tmp

    @contextlib.contextmanager
    def new_tree(self, tree_id, base_id=None):
        with tempfile.TemporaryDirectory(dir=self.store) as tmp:
            # the tree that is yielded will be added to the content store
            # on success as tree_id

            tree = f"{tmp}/tree"
            link = f"{tmp}/link"
            os.mkdir(tree, mode=0o755)

            if base_id:
                # the base, the working tree and the output tree are all on
                # the same fs, so attempt a lightweight copy if the fs
                # supports it
                subprocess.run(["cp", "--reflink=auto", "-a", f"{self.refs}/{base_id}/.", tree], check=True)

            yield tree

            # if the yield raises an exception, the working tree is cleaned
            # up by tempfile, otherwise, we save it in the correct place:
            fd = os.open(tree, os.O_DIRECTORY)
            try:
                m = hashlib.sha256()
                treesum.treesum(m, fd)
                treesum_hash = m.hexdigest()
            finally:
                os.close(fd)
            # the tree is stored in the objects directory using its content
            # hash as its name, ideally a given tree_id (i.e., given config)
            # will always produce the same content hash, but that is not
            # guaranteed
            output_tree = f"{self.objects}/{treesum_hash}"
            try:
                os.rename(tree, output_tree)
            except OSError as e:
                if e.errno == errno.ENOTEMPTY:
                    pass # tree with the same content hash already exist, use that
                else:
                    raise
            # symlink the tree_id (config hash) in the refs directory to the treesum
            # (content hash) in the objects directory. If a symlink by that name
            # alreday exists, atomically replace it, but leave the backing object
            # in place (it may be in use).
            os.symlink(f"../objects/{treesum_hash}", link)
            os.replace(link, f"{self.refs}/{tree_id}")
