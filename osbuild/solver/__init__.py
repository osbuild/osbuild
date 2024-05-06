import abc
import os
import urllib.error
import urllib.parse
import urllib.request


class Solver(abc.ABC):
    @abc.abstractmethod
    def dump(self):
        pass

    @abc.abstractmethod
    def depsolve(self, arguments):
        pass

    @abc.abstractmethod
    def search(self, args):
        pass


class SolverBase(Solver):
    # put any shared helpers in here
    pass


class SolverException(Exception):
    pass


class GPGKeyReadError(SolverException):
    pass


class TransactionError(SolverException):
    pass


class RepoError(SolverException):
    pass


class MarkingError(SolverException):
    pass


class DepsolveError(SolverException):
    pass


def modify_rootdir_path(path, root_dir):
    if path and root_dir:
        # if the root_dir is set, we need to translate the key path to be under this directory
        return os.path.join(root_dir, path.lstrip("/"))
    return path


def read_keys(paths, root_dir=None):
    keys = []
    for path in paths:
        url = urllib.parse.urlparse(path)
        if url.scheme == "file":
            path = url.path
            path = modify_rootdir_path(path, root_dir)
            try:
                with open(path, mode="r", encoding="utf-8") as keyfile:
                    keys.append(keyfile.read())
            except Exception as e:
                raise GPGKeyReadError(f"error loading gpg key from {path}: {e}") from e
        elif url.scheme in ["http", "https"]:
            try:
                resp = urllib.request.urlopen(urllib.request.Request(path))
                keys.append(resp.read().decode())
            except urllib.error.URLError as e:
                raise GPGKeyReadError(f"error reading remote gpg key at {path}: {e}") from e
        else:
            raise GPGKeyReadError(f"unknown url scheme for gpg key: {url.scheme} ({path})")
    return keys
