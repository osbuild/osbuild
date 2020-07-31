"""Build Roots

This implements the file-system environment available to osbuild modules. It
uses `bubblewrap` to contain osbuild modules in a private environment with as
little access to the outside as possible.
"""

import contextlib
import importlib
import importlib.util
import os
import stat
import subprocess
import tempfile


__all__ = [
    "BuildRoot",
]


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
    """

    def __init__(self, root, runner, libdir, path="/run/osbuild", var="/var/tmp"):
        self._exitstack = None
        self._rootdir = root
        self._rundir = path
        self._vardir = var
        self._libdir = libdir
        self._runner = runner
        self._apis = []
        self.dev = None
        self.var = None

    @staticmethod
    def _mknod(path, name, mode, major, minor):
        os.mknod(os.path.join(path, name),
                 mode=(stat.S_IMODE(mode) | stat.S_IFCHR),
                 device=os.makedev(major, minor))

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
            var = tempfile.TemporaryDirectory(prefix="osbuild-var-", dir=self._vardir)
            self.var = self._exitstack.enter_context(var)

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

    def register_api(self, api: "BaseAPI"):
        """Register an API endpoint.

        The context of the API endpoint will be bound to the context of
        this `BuildRoot`.
        """
        self._apis.append(api)

        if self._exitstack:
            self._exitstack.enter_context(api)

    def run(self, argv, binds=None, readonly_binds=None):
        """Runs a command in the buildroot.

        Takes the command and arguments, as well as bind mounts to mirror
        in the build-root for this command.

        This must be called from within an active context of this buildroot
        context-manager.
        """

        if not self._exitstack:
            raise RuntimeError("No active context")

        mounts = []

        # Import directories from the caller-provided root.
        for p in ["boot", "usr"]:
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
        mounts += ["--bind", "/sys", "/sys"]

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

        cmd = [
            "bwrap",
            "--cap-add", "CAP_MAC_ADMIN",
            "--chdir", "/",
            "--die-with-parent",
            "--new-session",
            "--setenv", "PATH", "/usr/sbin:/usr/bin",
            "--setenv", "PYTHONPATH", "/run/osbuild/lib",
            "--unshare-ipc",
            "--unshare-pid",
            "--unshare-net"
        ]

        cmd += mounts
        cmd += ["--", f"/run/osbuild/lib/runners/{self._runner}"]
        cmd += argv

        return subprocess.run(cmd,
                              check=False,
                              stdin=subprocess.DEVNULL)
