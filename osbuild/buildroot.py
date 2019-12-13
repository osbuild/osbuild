
import os
import platform
import shutil
import subprocess
import tempfile


__all__ = [
    "BuildRoot",
]


class BuildRoot:
    def __init__(self, root, runner, path="/run/osbuild", libdir=None):
        self.root = tempfile.mkdtemp(prefix="osbuild-buildroot-", dir=path)
        self.api = tempfile.mkdtemp(prefix="osbuild-api-", dir=path)
        self.var = tempfile.mkdtemp(prefix="osbuild-var-", dir="/var/tmp")
        self.mounts = []
        self.libdir = libdir or "/usr/lib/osbuild"
        self.runner = runner

        self.mount_root(root)
        self.mount_var()

    def mount_root(self, root):
        for p in ["usr", "bin", "sbin", "lib", "lib64"]:
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

        # pylint suggests to epxlicitly pass `check` to subprocess.run()
        check = kwargs.pop("check", False)

        # we need read-write access to loopback devices
        loopback_allow = "rw"
        if platform.machine() == "s390x":
            # on s390x, the bootloader installation program (zipl)
            # wants to be able create devices nodes, so allow that
            loopback_allow += "m"

        return subprocess.run([
            "systemd-nspawn",
            "--quiet",
            "--register=no",
            "--as-pid2",
            "--link-journal=no",
            f"--property=DeviceAllow=block-loop {loopback_allow}",
            f"--directory={self.root}",
            f"--bind-ro={self.libdir}:/run/osbuild/lib",
            *[f"--bind={b}" for b in (binds or [])],
            *[f"--bind-ro={b}" for b in [f"{self.api}:/run/osbuild/api"] + (readonly_binds or [])],
            f"/run/osbuild/lib/runners/{self.runner}"
            ] + argv, check=check, **kwargs)

    def __del__(self):
        self.unmount()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.unmount()
