"""Checksum Utilities

Small convenience functions to work with checksums.
"""
import hashlib
import os

from .types import PathLike

# How many bytes to read in one go. Taken from coreutils/gnulib
BLOCKSIZE = 32768


def hexdigest_file(path: PathLike, algorithm: str) -> str:
    """Return the hexdigest of the file at `path` using `algorithm`

    Will stream the contents of file to the hash `algorithm` and
    return the hexdigest. If the specified `algorithm` is not
    supported a `ValueError` will be raised.
    """
    hasher = hashlib.new(algorithm)

    with open(path, "rb") as f:

        os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_SEQUENTIAL)

        while True:
            data = f.read(BLOCKSIZE)
            if not data:
                break

            hasher.update(data)

    return hasher.hexdigest()


def verify_file(path: PathLike, checksum: str) -> bool:
    """Hash the file and return if the specified `checksum` matches

    Uses `hexdigest_file` to hash the contents of the file at
    `path` and return if the hexdigest matches the one specified
    in `checksum`, where `checksum` consist of the algorithm used
    and the digest joined via `:`, e.g. `sha256:abcd...`.
    """
    algorithm, want = checksum.split(":", 1)

    have = hexdigest_file(path, algorithm)

    return have == want
