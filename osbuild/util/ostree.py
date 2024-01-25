import collections
import contextlib
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import typing
# pylint doesn't understand the string-annotation below
from typing import Any, Dict, List, Tuple  # pylint: disable=unused-import

from osbuild.util.rhsm import Subscriptions

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
      - selinux-label-version: commit

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
        "selinux-label-version": Param(int),
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

            with os.fdopen(fd, "w+", encoding="utf8") as f:
                self.dump(f)

            yield name
        finally:
            if name:
                os.unlink(name)


def setup_remote(repo, name, remote):
    """Configure an OSTree remote in a given repo"""

    url = remote["url"]
    gpg = remote.get("gpgkeys", [])

    remote_add_args = []
    if not gpg:
        remote_add_args = ["--no-gpg-verify"]

    if "contenturl" in remote:
        remote_add_args.append(f"--contenturl={remote['contenturl']}")

    if remote.get("secrets", {}).get("name") == "org.osbuild.rhsm.consumer":
        secrets = Subscriptions.get_consumer_secrets()
        remote_add_args.append(f"--set=tls-client-key-path={secrets['consumer_key']}")
        remote_add_args.append(f"--set=tls-client-cert-path={secrets['consumer_cert']}")

    cli("remote", "add", name, url,
        *remote_add_args, repo=repo)

    for key in gpg:
        cli("remote", "gpg-import", "--stdin",
            name, repo=repo, _input=key)


def rev_parse(repo: PathLike, ref: str) -> str:
    """Resolve an OSTree reference `ref` in the repository at `repo`"""

    repo = os.fspath(repo)

    if isinstance(repo, bytes):
        repo = repo.decode("utf8")

    r = subprocess.run(["ostree", "rev-parse", ref, f"--repo={repo}"],
                       encoding="utf8",
                       stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT,
                       check=False)

    msg = r.stdout.strip()
    if r.returncode != 0:
        raise RuntimeError(msg)

    return msg


def show(repo: PathLike, checksum: str) -> str:
    """Show the metada of an OSTree object pointed by `checksum` in the repository at `repo`"""

    repo = os.fspath(repo)

    if isinstance(repo, bytes):
        repo = repo.decode("utf8")

    r = subprocess.run(["ostree", "show", f"--repo={repo}", checksum],
                       encoding="utf8",
                       stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT,
                       check=False)

    msg = r.stdout.strip()
    if r.returncode != 0:
        raise RuntimeError(msg)

    return msg


def pull_local(source_repo: PathLike, target_repo: PathLike, remote: str, ref: str):
    """Run ostree-pull local to copy commits around"""

    extra_args = []
    if remote:
        extra_args.append(f'--remote={remote}')

    cli("pull-local", source_repo, ref,
        *extra_args,
        repo=target_repo)


def cli(*args, _input=None, **kwargs):
    """Thin wrapper for running the ostree CLI"""
    args = list(args) + [f'--{k}={v}' for k, v in kwargs.items()]
    print("ostree " + " ".join(args), file=sys.stderr)
    return subprocess.run(["ostree"] + args,
                          encoding="utf8",
                          stdout=subprocess.PIPE,
                          input=_input,
                          check=True)


def parse_input_commits(commits):
    """Parse ostree input commits and return the repo path and refs specified"""
    data = commits["data"]
    refs = data["refs"]
    assert refs, "Need at least one commit"
    return commits["path"], data["refs"]


def parse_deployment_option(root: PathLike, deployment: Dict) -> Tuple[str, str, str]:
    """Parse the deployment option and return the osname, ref, and serial

    The `deployment` arg contains the following sub fields:
    - osname: Name of the stateroot used in the deployment (ie. fedora-coreos)
    - ref: OStree ref to used for the deployment (ie. fedora/aarch64/coreos/next)
    - serial: The deployment serial (ie. 0)
    - default: Boolean to determine whether the default ostree deployment should be used
    """

    default_deployment = deployment.get("default")
    if default_deployment:
        filenames = glob.glob(os.path.join(root, 'ostree/deploy/*/deploy/*.0'))
        if len(filenames) < 1:
            raise ValueError("Could not find deployment")
        if len(filenames) > 1:
            raise ValueError(f"More than one deployment found: {filenames}")

        # We pick up the osname, commit, and serial from the filesystem
        # here. We'll return the detected commit as the ref in this
        # since it's a valid substitute for all subsequent uses in
        # the code base.
        f = re.search("/ostree/deploy/(.*)/deploy/(.*)\\.([0-9])", filenames[0])
        if not f:
            raise ValueError("cannot find ostree deployment in {filenames[0]}")
        osname = f.group(1)
        commit = f.group(2)
        serial = f.group(3)
        return osname, commit, serial

    osname = deployment["osname"]
    ref = deployment["ref"]
    serial = deployment.get("serial", 0)
    return osname, ref, serial


def deployment_path(root: PathLike, osname: str = "", ref: str = "", serial: int = 0):
    """Return the path to a deployment given the parameters"""

    base = os.path.join(root, "ostree")

    repo = os.path.join(base, "repo")
    stateroot = os.path.join(base, "deploy", osname)

    commit = rev_parse(repo, ref)
    sysroot = f"{stateroot}/deploy/{commit}.{serial}"

    return sysroot


def parse_origin(origin: PathLike):
    """Parse the origin file and return the deployment type and imgref

    Example container case: container-image-reference=ostree-remote-image:fedora:docker://quay.io/fedora/fedora-coreos:stable
    Example ostree commit case: refspec=fedora:fedora/x86_64/coreos/stable
    """
    deploy_type = ""
    imgref = ""
    with open(origin, "r", encoding="utf8") as f:
        for line in f:
            separated_line = line.split("=")
            if separated_line[0] == "container-image-reference":
                deploy_type = "container"
                imgref = separated_line[1].rstrip()
                break
            if separated_line[0] == "refspec":
                deploy_type = "ostree_commit"
                imgref = separated_line[1].rstrip()
                break

    if deploy_type == "":
        raise ValueError("Could not find 'container-image-reference' or 'refspec' in origin file")
    if imgref == "":
        raise ValueError("Could not find imgref in origin file")

    return deploy_type, imgref


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
        return {line.split(':')[0]: line for line in lines}


class SubIdsDB:
    """Represention of subordinate Ids database

    Class to represent a mapping of a user name to subordinate ids,
    like `/etc/subgid` and `/etc/subuid`.
    """

    def __init__(self) -> None:
        self.db: 'collections.OrderedDict[str, Any]' = collections.OrderedDict()

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
        data = "\n".join([
            f"{name}:{uid}:{count}\n"
            for name, (uid, count) in self.db.items()
        ])

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
