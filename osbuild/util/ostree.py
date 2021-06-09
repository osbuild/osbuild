import contextlib
import json
import os
import subprocess
import tempfile
import typing

from typing import List

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
            fd, name = tempfile.mkstemp(suffix=".json",
                                        text=True)

            with os.fdopen(fd, "w+") as f:
                self.dump(f)

            yield name
        finally:
            if name:
                os.unlink(name)


def rev_parse(repo: PathLike, ref: str) -> str:
    """Resolve an OSTree reference `ref` in the repository at `repo`"""

    repo = os.fspath(repo)

    r = subprocess.run(["ostree", "rev-parse", ref, f"--repo={repo}"],
                       encoding="utf-8",
                       stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT,
                       check=False)

    msg = r.stdout.strip()
    if r.returncode != 0:
        raise RuntimeError(msg)

    return msg
