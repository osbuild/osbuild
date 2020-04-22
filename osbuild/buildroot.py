
import contextlib
import importlib
import importlib.util
import os
import platform
import shutil
import subprocess
import tempfile


__all__ = [
    "BuildRoot",
]


class BuildRoot(contextlib.AbstractContextManager):
    def __init__(self, root, runner, path="/run/osbuild", libdir=None, var="/var/tmp"):
        self.root = tempfile.mkdtemp(prefix="osbuild-buildroot-", dir=path)
        self.api = tempfile.mkdtemp(prefix="osbuild-api-", dir=path)
        self.var = tempfile.mkdtemp(prefix="osbuild-var-", dir=var)
        self.mounts = []
        self.libdir = libdir
        self.runner = runner

        self.mount_root(root)
        self.mount_var()

    def mount_root(self, root):
        for p in ["boot", "usr", "bin", "sbin", "lib", "lib64"]:
            source = os.path.join(root, p)
            target = os.path.join(self.root, p)
            if not os.path.isdir(source) or os.path.islink(source):
                continue # only bind-mount real dirs
            os.mkdir(target)
            try:
                subprocess.run(["mount", "-o", "bind,ro", source, target], check=True)
            except subprocess.CalledProcessError:
                self.unmount()
                raise
            self.mounts.append(target)

        if platform.machine() == "s390x" or platform.machine() == "ppc64le":
            # work around a combination of systemd not creating the link from
            # /lib64 -> /usr/lib64 (see systemd issue #14311) and the dynamic
            # linker is being set to (/lib/ld64.so.1 -> /lib64/ld64.so.1)
            # on s390x or /lib64/ld64.so.2 on ppc64le
            # Therefore we manually create the link before calling nspawn
            os.symlink("/usr/lib64", f"{self.root}/lib64")

    def mount_var(self):
        target = os.path.join(self.root, "var")
        os.mkdir(target)
        try:
            subprocess.run(["mount", "-o", "bind", self.var, target], check=True)
        except subprocess.CalledProcessError:
            self.unmount()
            raise
        self.mounts.append(target)

    def unmount(self):
        for path in self.mounts:
            subprocess.run(["umount", "--lazy", path], check=True)
            os.rmdir(path)
        self.mounts = []
        if self.root:
            shutil.rmtree(self.root)
            self.root = None
        if self.api:
            shutil.rmtree(self.api)
            self.api = None
        if self.var:
            shutil.rmtree(self.var)
            self.var = None

    def run(self, argv, binds=None, readonly_binds=None, **kwargs):
        """Runs a command in the buildroot.

        Its arguments mean the same as those for subprocess.run().
        """

        nspawn_ro_binds = []

        # pylint suggests to epxlicitly pass `check` to subprocess.run()
        check = kwargs.pop("check", False)

        # we need read-write access to loopback devices
        loopback_allow = "rw"
        if platform.machine() == "s390x":
            # on s390x, the bootloader installation program (zipl)
            # wants to be able create devices nodes, so allow that
            loopback_allow += "m"

        # make osbuild API-calls accessible to the container
        nspawn_ro_binds.append(f"{self.api}:/run/osbuild/api")

        # We want to execute our stages and other scripts in the container. So
        # far, we do not install osbuild as a package in the container, but
        # provide it from the outside. Therefore, we need to provide `libdir`
        # via bind-mount. Furthermore, a system-installed `libdir` has the
        # python packages separate in `site-packages`, so we need to bind-mount
        # them as well.
        # In the future, we want to work towards mandating an osbuild package to
        # be installed in the container, so the build is self-contained and does
        # not take scripts from the host. However, this requires osbuild
        # packaged for those containers. Furthermore, we want to keep supporting
        # the current import-model for testing and development.
        if self.libdir is not None:
            # caller-specified `libdir` must be self-contained
            nspawn_ro_binds.append(f"{self.libdir}:/run/osbuild/lib")
        else:
            # system `libdir` requires importing the python module
            nspawn_ro_binds.append(f"/usr/lib/osbuild:/run/osbuild/lib")
            modorigin = importlib.util.find_spec('osbuild').origin
            modpath = os.path.dirname(modorigin)
            nspawn_ro_binds.append(f"{modpath}:/run/osbuild/lib/osbuild")

        return subprocess.run([
            "systemd-nspawn",
            "--quiet",
            "--register=no",
            "--keep-unit",
            "--as-pid2",
            "--link-journal=no",
            f"--property=DeviceAllow=block-loop {loopback_allow}",
            f"--directory={self.root}",
            *[f"--bind-ro={b}" for b in nspawn_ro_binds],
            *[f"--bind={b}" for b in (binds or [])],
            *[f"--bind-ro={b}" for b in (readonly_binds or [])],
            f"/run/osbuild/lib/runners/{self.runner}"
            ] + argv, check=check, **kwargs)

    def __del__(self):
        self.unmount()

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.unmount()
