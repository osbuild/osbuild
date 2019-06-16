
import json
import os
import subprocess
import sys
import tempfile


__all__ = [
    "StageFailed",
    "BuildRoot",
    "tmpfs"
]


libdir = os.path.dirname(__file__)
if not os.path.exists(f"{libdir}/stages"):
    libdir = f"{sys.prefix}/lib"


class StageFailed(Exception):
    def __init__(self, stage, returncode):
        self.stage = stage
        self.returncode = returncode


class tmpfs:
    def __init__(self, path="/run/osbuild"):
        self.root = tempfile.mkdtemp(prefix="osbuild-tmpfs-", dir=path)
        self.mounted = False
        try:
            subprocess.run(["mount", "-t", "tmpfs", "tmpfs", self.root], check=True)
            self.mounted = True
        except subprocess.CalledProcessError:
            self.unmount()

    def unmount(self):
        if not self.root:
            return
        if self.mounted:
            subprocess.run(["umount", "--lazy", self.root], check=True)
        os.rmdir(self.root)
        self.root = None

    def __del__(self):
        self.unmount()

    def __enter__(self):
        return self.root

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.unmount()


class BuildRoot:
    def __init__(self, path="/run/osbuild"):
        self.root = tempfile.mkdtemp(prefix="osbuild-buildroot-", dir=path)
        self.mounted = False
        try:
            subprocess.run(["mount", "-o", "bind,ro", "/", self.root], check=True)
            self.mounted = True
        except subprocess.CalledProcessError:
            self.unmount()
            raise

        # systemd-nspawn silently removes some characters when choosing a
        # machine name from the directory name. The only one relevant for
        # us is '_', because all other characters used by
        # TemporaryDirectory() are allowed. Replace it with 'L's
        # (TemporaryDirectory() only uses lower-case characters)
        self.machine_name = os.path.basename(self.root).replace("_", "L")

    def unmount(self):
        if not self.root:
            return
        if self.mounted:
            subprocess.run(["umount", "--lazy", self.root], check=True)
        os.rmdir(self.root)
        self.root = None

    def run(self, argv, binds=[], readonly_binds=[], *args, **kwargs):
        return subprocess.run([
            "systemd-nspawn",
            "--quiet",
            "--as-pid2",
            "--link-journal=no",
            "--volatile=yes",
            f"--machine={self.machine_name}",
            f"--directory={self.root}",
            f"--bind={libdir}/osbuild-run:/run/osbuild/osbuild-run",
            *[f"--bind={b}" for b in binds],
            *[f"--bind-ro={b}" for b in readonly_binds],
            "/run/osbuild/osbuild-run",
        ] + argv, *args, **kwargs)

    def _get_system_resources_from_etc(self, stage_or_assembler):
        resources = stage_or_assembler.get("systemResourcesFromEtc", [])
        for r in resources:
            if not r.startswith("/etc"):
                raise ValueError(f"{r} is not a resource in /etc/")
            if ":" in r:
                raise ValueError(f"{r} tries to bind to a different location")
        return resources

    def run_stage(self, stage, tree, input_dir=None):
        name = stage["name"]
        args = {
            "tree": "/run/osbuild/tree",
            "options": stage.get("options", {})
        }

        robinds = [f"{libdir}/stages/{name}:/run/osbuild/{name}"]
        robinds.extend(self._get_system_resources_from_etc(stage))

        binds = [f"{tree}:/run/osbuild/tree"]
        if input_dir:
            robinds.append(f"{input_dir}:/run/osbuild/input")
            args["input_dir"] = "/run/osbuild/input"

        try:
            self.run([f"/run/osbuild/{name}"], binds=binds, readonly_binds=robinds, input=json.dumps(args), encoding="utf-8", check=True)
        except subprocess.CalledProcessError as error:
            raise StageFailed(name, error.returncode)

    def run_assembler(self, assembler, tree, input_dir=None, output_dir=None):
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        name = assembler["name"]
        args = {
            "tree": "/run/osbuild/tree",
            "options": assembler.get("options", {}),
        }
        robinds = [
            f"{tree}:/run/osbuild/tree",
            f"{libdir}/assemblers/{name}:/run/osbuild/{name}"
        ]
        robinds.extend(self._get_system_resources_from_etc(assembler))
        binds = []

        if input_dir:
            robinds.append(f"{input_dir}:/run/osbuild/input")
            args["input_dir"] = "/run/osbuild/input"
        if output_dir:
            binds.append(f"{output_dir}:/run/osbuild/output")
            args["output_dir"] = "/run/osbuild/output"

        try:
            self.run([f"/run/osbuild/{name}"], binds=binds, readonly_binds=robinds, input=json.dumps(args), encoding="utf-8", check=True)
        except subprocess.CalledProcessError as error:
            raise StageFailed(name, error.returncode)

    def __del__(self):
        self.unmount()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.unmount()
