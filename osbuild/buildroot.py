"""Build Roots

This implements the file-system environment available to osbuild modules. It
uses `bubblewrap` to contain osbuild modules in a private environment with as
little access to the outside as possible.
"""

import contextlib
import importlib
import importlib.util
import io
import os
import select
import stat
import subprocess
import tempfile
import time
from typing import Set

from osbuild.api import BaseAPI
from osbuild.util import linux

__all__ = [
    "BuildRoot",
]


class CompletedBuild:
    """The result of a `BuildRoot.run`

    Contains the actual `process` that was executed but also has
    convenience properties to quickly access the `returncode` and
    `output`. The latter is also provided via `stderr`, `stdout`
    properties, making it a drop-in replacement for `CompletedProcess`.
    """

    def __init__(self, proc: subprocess.CompletedProcess, output: str):
        self.process = proc
        self.output = output

    @property
    def returncode(self):
        return self.process.returncode

    @property
    def stdout(self):
        return self.output

    @property
    def stderr(self):
        return self.output


class ProcOverrides:
    """Overrides for /proc inside the buildroot"""

    def __init__(self, path) -> None:
        self.path = path
        self.overrides: Set["str"] = set()

    @property
    def cmdline(self) -> str:
        with open(os.path.join(self.path, "cmdline"), "r", encoding="utf8") as f:
            return f.read().strip()

    @cmdline.setter
    def cmdline(self, value) -> None:
        with open(os.path.join(self.path, "cmdline"), "w", encoding="utf8") as f:
            f.write(value + "\n")
        self.overrides.add("cmdline")


# pylint: disable=too-many-instance-attributes
class BuildRoot(contextlib.AbstractContextManager):
    """Build Root

    This class implements a context-manager that maintains a root file-system
    for contained environments. When entering the context, the required
    file-system setup is performed, and it is automatically torn down when
    exiting.

    The `run()` method allows running applications in this environment. Some
    state is persistent across runs, including data in `/var`. It is deleted
    only when exiting the context manager.

    If `BuildRoot.caps` is not `None`, only the capabilities listed in this
    set will be retained (all others will be dropped), otherwise all caps
    are retained.
    """

    def __init__(self, root, runner, libdir, var, *, rundir="/run/osbuild"):
        self._exitstack = None
        self._rootdir = root
        self._rundir = rundir
        self._vardir = var
        self._libdir = libdir
        self._runner = runner
        self._apis = []
        self.dev = None
        self.var = None
        self.proc = None
        self.tmp = None
        self.mount_boot = True
        self.caps = None

    @staticmethod
    def _mknod(path, name, mode, major, minor):
        os.mknod(os.path.join(path, name), mode=(stat.S_IMODE(mode) | stat.S_IFCHR), device=os.makedev(major, minor))

    def __enter__(self):
        self._exitstack = contextlib.ExitStack()
        with self._exitstack:
            # We create almost everything directly in the container as temporary
            # directories and mounts. However, for some things we need external
            # setup. For these, we create temporary directories which are then
            # bind-mounted into the container.
            #
            # For now, this includes:
            #
            #   * We create a tmpfs instance *without* `nodev` which we then use
            #     as `/dev` in the container. This is required for the container
            #     to create device nodes for loop-devices.
            #
            #   * We create a temporary directory for variable data and then use
            #     it as '/var' in the container. This allows the container to
            #     create throw-away data that it does not want to put into a
            #     tmpfs.

            os.makedirs(self._rundir, exist_ok=True)
            dev = tempfile.TemporaryDirectory(prefix="osbuild-dev-", dir=self._rundir)
            self.dev = self._exitstack.enter_context(dev)

            os.makedirs(self._vardir, exist_ok=True)
            tmp = tempfile.TemporaryDirectory(prefix="osbuild-tmp-", dir=self._vardir)
            self.tmp = self._exitstack.enter_context(tmp)

            self.var = os.path.join(self.tmp, "var")
            os.makedirs(self.var, exist_ok=True)

            proc = os.path.join(self.tmp, "proc")
            os.makedirs(proc)
            self.proc = ProcOverrides(proc)
            self.proc.cmdline = "root=/dev/osbuild"

            subprocess.run(["mount", "-t", "tmpfs", "-o", "nosuid", "none", self.dev], check=True)
            self._exitstack.callback(lambda: subprocess.run(["umount", "--lazy", self.dev], check=True))

            self._mknod(self.dev, "full", 0o666, 1, 7)
            self._mknod(self.dev, "null", 0o666, 1, 3)
            self._mknod(self.dev, "random", 0o666, 1, 8)
            self._mknod(self.dev, "urandom", 0o666, 1, 9)
            self._mknod(self.dev, "tty", 0o666, 5, 0)
            self._mknod(self.dev, "zero", 0o666, 1, 5)

            # Prepare all registered API endpoints
            for api in self._apis:
                self._exitstack.enter_context(api)

            self._exitstack = self._exitstack.pop_all()

        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self._exitstack.close()
        self._exitstack = None

    def register_api(self, api: BaseAPI):
        """Register an API endpoint.

        The context of the API endpoint will be bound to the context of
        this `BuildRoot`.
        """
        self._apis.append(api)

        if self._exitstack:
            self._exitstack.enter_context(api)

    def run(self, argv, monitor, timeout=None, binds=None, readonly_binds=None, extra_env=None):
        """Runs a command in the buildroot.

        Takes the command and arguments, as well as bind mounts to mirror
        in the build-root for this command.

        This must be called from within an active context of this buildroot
        context-manager.

        Returns a `CompletedBuild` object.
        """

        if not self._exitstack:
            raise RuntimeError("No active context")

        mounts = []

        # Import directories from the caller-provided root.
        imports = ["usr"]
        if self.mount_boot:
            imports.insert(0, "boot")

        for p in imports:
            source = os.path.join(self._rootdir, p)
            if os.path.isdir(source) and not os.path.islink(source):
                mounts += ["--ro-bind", source, os.path.join("/", p)]

        # Create /usr symlinks.
        mounts += ["--symlink", "usr/lib", "/lib"]
        mounts += ["--symlink", "usr/lib64", "/lib64"]
        mounts += ["--symlink", "usr/bin", "/bin"]
        mounts += ["--symlink", "usr/sbin", "/sbin"]

        # Setup /dev.
        mounts += ["--dev-bind", self.dev, "/dev"]
        mounts += ["--tmpfs", "/dev/shm"]

        # Setup temporary/data file-systems.
        mounts += ["--dir", "/etc"]
        mounts += ["--tmpfs", "/run"]
        mounts += ["--tmpfs", "/tmp"]
        mounts += ["--bind", self.var, "/var"]

        # Setup API file-systems.
        mounts += ["--proc", "/proc"]
        mounts += ["--ro-bind", "/sys", "/sys"]
        mounts += ["--ro-bind-try", "/sys/fs/selinux", "/sys/fs/selinux"]

        # There was a bug in mke2fs (fixed in versionv 1.45.7) where mkfs.ext4
        # would fail because the default config, created on the fly, would
        # contain a syntax error. Therefore we bind mount the config from
        # the build root, if it exists
        mounts += ["--ro-bind-try", os.path.join(self._rootdir, "etc/mke2fs.conf"), "/etc/mke2fs.conf"]

        # Skopeo needs things like /etc/containers/policy.json, so take them from buildroot
        mounts += ["--ro-bind-try", os.path.join(self._rootdir, "etc/containers"), "/etc/containers"]

        # We execute our own modules by bind-mounting them from the host into
        # the build-root. We have minimal requirements on the build-root, so
        # these modules can be executed. Everything else we provide ourselves.
        # In case `libdir` contains the python module, it must be self-contained
        # and we provide nothing else. Otherwise, we additionally look for
        # the installed `osbuild` module and bind-mount it as well.
        mounts += ["--ro-bind", f"{self._libdir}", "/run/osbuild/lib"]
        if not os.listdir(os.path.join(self._libdir, "osbuild")):
            modorigin = importlib.util.find_spec("osbuild").origin
            modpath = os.path.dirname(modorigin)
            mounts += ["--ro-bind", f"{modpath}", "/run/osbuild/lib/osbuild"]

        # Setup /proc overrides
        for override in self.proc.overrides:
            mounts += ["--ro-bind", os.path.join(self.proc.path, override), os.path.join("/proc", override)]

        # Make caller-provided mounts available as well.
        for b in binds or []:
            mounts += ["--bind"] + b.split(":")
        for b in readonly_binds or []:
            mounts += ["--ro-bind"] + b.split(":")

        # Prepare all registered API endpoints: bind mount the address with
        # the `endpoint` name, provided by the API, into the well known path
        mounts += ["--dir", "/run/osbuild/api"]
        for api in self._apis:
            api_path = "/run/osbuild/api/" + api.endpoint
            mounts += ["--bind", api.socket_address, api_path]

        # Bind mount the runner into the container at a well known location
        runner_name = os.path.basename(self._runner)
        runner = f"/run/osbuild/runner/{runner_name}"
        mounts += ["--ro-bind", self._runner, runner]

        cmd = [
            "bwrap",
            "--chdir",
            "/",
            "--die-with-parent",
            "--new-session",
            "--unshare-ipc",
            "--unshare-pid",
            "--unshare-net",
        ]

        cmd += self.build_capabilities_args()

        cmd += mounts
        cmd += ["--", runner]
        cmd += argv

        # Setup a new environment for the container.
        env = {
            "container": "bwrap-osbuild",
            "LC_CTYPE": "C.UTF-8",
            "PATH": "/usr/sbin:/usr/bin",
            "PYTHONPATH": "/run/osbuild/lib",
            "PYTHONUNBUFFERED": "1",
            "TERM": os.getenv("TERM", "dumb"),
        }
        if extra_env:
            env.update(extra_env)

        proc = subprocess.Popen(
            cmd,
            bufsize=0,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )

        data = io.StringIO()
        start = time.monotonic()
        READ_ONLY = select.POLLIN | select.POLLPRI | select.POLLHUP | select.POLLERR
        poller = select.poll()
        poller.register(proc.stdout.fileno(), READ_ONLY)
        while True:
            buf = self.read_with_timeout(proc, poller, start, timeout)
            if not buf:
                break

            txt = buf.decode("utf-8")
            data.write(txt)
            monitor.log(txt)

        poller.unregister(proc.stdout.fileno())
        buf, _ = proc.communicate()
        txt = buf.decode("utf-8")
        monitor.log(txt)
        data.write(txt)
        output = data.getvalue()
        data.close()

        return CompletedBuild(proc, output)

    def build_capabilities_args(self):
        """Build the capabilities arguments for bubblewrap"""
        args = []

        # If no capabilities are explicitly requested we retain all of them
        if self.caps is None:
            return args

        # Under the assumption that we are running as root, the capabilities
        # for the child process (bubblewrap) are calculated as follows:
        #   P'(effective) = P'(permitted)
        #   P'(permitted) = P(inheritable) | P(bounding)
        # Thus bubblewrap will effectively run with all capabilities that
        # are present in the bounding set. If run as root, bubblewrap will
        # preserve all capabilities in the effective set when running the
        # container, which corresponds to our bounding set.
        # Therefore: drop all capabilities present in the bounding set minus
        # the ones explicitly requested.
        have = linux.cap_bound_set()
        drop = have - self.caps

        for cap in sorted(drop):
            args += ["--cap-drop", cap]

        return args

    @classmethod
    def read_with_timeout(cls, proc, poller, start, timeout):
        fd = proc.stdout.fileno()
        if timeout is None:
            return os.read(fd, 32768)

        # convert timeout to milliseconds
        remaining = (timeout * 1000) - (time.monotonic() - start)
        if remaining <= 0:
            proc.terminate()
            raise TimeoutError

        buf = None
        events = poller.poll(remaining)
        if not events:
            proc.terminate()
            raise TimeoutError
        for fd, flag in events:
            if flag & (select.POLLIN | select.POLLPRI):
                buf = os.read(fd, 32768)
            if flag & (select.POLLERR | select.POLLHUP):
                proc.terminate()
        return buf
