import collections
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import typing

# pylint doesn't understand the string-annotation below
from typing import Any, List  # pylint: disable=unused-import

from .types import PathLike


class Param:
    """rpm-ostree Treefile parameter"""

    def __init__(self, value_type, mandatory=False):
        self.type = value_type
        self.mandatory = mandatory

    def check(self, value):
        origin = getattr(self.type, "__origin__", None)
        if origin:
            self.typecheck(value, origin)
            if origin is list or origin is typing.List:
                self.check_list(value, self.type)
            else:
                raise NotImplementedError(origin)
        else:
            self.typecheck(value, self.type)

    @staticmethod
    def check_list(value, tp):
        inner = tp.__args__
        for x in value:
            Param.typecheck(x, inner)

    @staticmethod
    def typecheck(value, tp):
        if isinstance(value, tp):
            return
        raise ValueError(f"{value} is not of {tp}")


class Treefile:
    """Representation of an rpm-ostree Treefile

    The following parameters are currently supported,
    presented together with the rpm-ostree compose
    phase that they are used in.
      - ref: commit
      - repos: install
      - selinux: install, postprocess, commit
      - boot-location: postprocess
      - etc-group-members: postprocess
      - machineid-compat

    NB: 'ref' and 'repos' are mandatory and must be
    present, even if they are not used in the given
    phase; they therefore have defaults preset.
    """

    parameters = {
        "ref": Param(str, True),
        "repos": Param(List[str], True),
        "selinux": Param(bool),
        "boot-location": Param(str),
        "etc-group-members": Param(List[str]),
        "machineid-compat": Param(bool),
        "initramfs-args": Param(List[str]),
    }

    def __init__(self):
        self._data = {}
        self["ref"] = "osbuild/devel"
        self["repos"] = ["osbuild"]

    def __getitem__(self, key):
        param = self.parameters.get(key)
        if not param:
            raise ValueError(f"Unknown param: {key}")
        return self._data[key]

    def __setitem__(self, key, value):
        param = self.parameters.get(key)
        if not param:
            raise ValueError(f"Unknown param: {key}")
        param.check(value)
        self._data[key] = value

    def dumps(self):
        return json.dumps(self._data)

    def dump(self, fp):
        return json.dump(self._data, fp)

    @contextlib.contextmanager
    def as_tmp_file(self):
        name = None
        try:
            fd, name = tempfile.mkstemp(suffix=".json", text=True)

            with os.fdopen(fd, "w+", encoding="utf8") as f:
                self.dump(f)

            yield name
        finally:
            if name:
                os.unlink(name)


def rev_parse(repo: PathLike, ref: str) -> str:
    """Resolve an OSTree reference `ref` in the repository at `repo`"""

    repo = os.fspath(repo)

    if isinstance(repo, bytes):
        repo = repo.decode("utf8")

    r = subprocess.run(
        ["ostree", "rev-parse", ref, f"--repo={repo}"],
        encoding="utf8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    msg = r.stdout.strip()
    if r.returncode != 0:
        raise RuntimeError(msg)

    return msg


def show(repo: PathLike, checksum: str) -> str:
    """Show the metada of an OSTree object pointed by `checksum` in the repository at `repo`"""

    repo = os.fspath(repo)

    if isinstance(repo, bytes):
        repo = repo.decode("utf8")

    r = subprocess.run(
        ["ostree", "show", f"--repo={repo}", checksum],
        encoding="utf8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    msg = r.stdout.strip()
    if r.returncode != 0:
        raise RuntimeError(msg)

    return msg


def deployment_path(root: PathLike, osname: str, ref: str, serial: int):
    """Return the path to a deployment given the parameters"""

    base = os.path.join(root, "ostree")

    repo = os.path.join(base, "repo")
    stateroot = os.path.join(base, "deploy", osname)

    commit = rev_parse(repo, ref)
    sysroot = f"{stateroot}/deploy/{commit}.{serial}"

    return sysroot


class PasswdLike:
    """Representation of a file with structure like /etc/passwd

    If each line in a file contains a key-value pair separated by the
    first colon on the line, it can be considered "passwd"-like. This
    class can parse the the list, manipulate it, and export it to file
    again.
    """

    def __init__(self):
        """Initialize an empty PasswdLike object"""
        self.db = {}

    @classmethod
    def from_file(cls, path: PathLike, allow_missing_file: bool = False):
        """Initialize a PasswdLike object from an existing file"""
        ret = cls()
        if allow_missing_file:
            if not os.path.isfile(path):
                return ret

        with open(path, "r", encoding="utf8") as p:
            ret.db = cls._passwd_lines_to_dict(p.readlines())
        return ret

    def merge_with_file(self, path: PathLike, allow_missing_file: bool = False):
        """Extend the database with entries from another file"""
        if allow_missing_file:
            if not os.path.isfile(path):
                return

        with open(path, "r", encoding="utf8") as p:
            additional_passwd_dict = self._passwd_lines_to_dict(p.readlines())
            for name, passwd_line in additional_passwd_dict.items():
                if name not in self.db:
                    self.db[name] = passwd_line

    def dump_to_file(self, path: PathLike):
        """Write the current database to a file"""
        with open(path, "w", encoding="utf8") as p:
            p.writelines(list(self.db.values()))

    @staticmethod
    def _passwd_lines_to_dict(lines):
        """Take a list of passwd lines and produce a "name": "line" dictionary"""
        return {line.split(":")[0]: line for line in lines}


class SubIdsDB:
    """Represention of subordinate Ids database

    Class to represent a mapping of a user name to subordinate ids,
    like `/etc/subgid` and `/etc/subuid`.
    """

    def __init__(self) -> None:
        self.db: "collections.OrderedDict[str, Any]" = collections.OrderedDict()

    def read(self, fp) -> int:
        idx = 0
        for idx, line in enumerate(fp.readlines()):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            comps = line.split(":")
            if len(comps) != 3:
                print(f"WARNING: invalid line `{line}`", file=sys.stderr)
                continue
            name, uid, count = comps
            self.db[name] = (uid, count)
        return idx

    def dumps(self) -> str:
        """Dump the database to a string"""
        data = "\n".join([f"{name}:{uid}:{count}\n" for name, (uid, count) in self.db.items()])

        return data

    def read_from(self, path: PathLike) -> int:
        """Read a file and add the entries to the database"""
        with open(path, "r", encoding="utf8") as f:
            return self.read(f)

    def write_to(self, path: PathLike) -> None:
        """Write the database to a file"""
        data = self.dumps()
        with open(path, "w", encoding="utf8") as f:
            f.write(data)

    def __bool__(self) -> bool:
        return bool(self.db)
