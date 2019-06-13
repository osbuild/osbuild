
import json
import os
import subprocess
import sys
import tempfile


__all__ = [
    "StageFailed",
    "BuildRoot"
]


libdir = os.path.dirname(__file__)
if not os.path.exists(f"{libdir}/stages"):
    libdir = f"{sys.prefix}/lib"


class StageFailed(Exception):
    def __init__(self, stage, returncode):
        self.stage = stage
        self.returncode = returncode


class BuildRoot:
    def __init__(self, path=None):
        self.buildroot = tempfile.mkdtemp(prefix="osbuild-buildroot-", dir=path)
        self.buildroot_mounted = False
        self.tree = tempfile.mkdtemp(prefix="osbuild-tree-", dir=path)
        self.tree_mounted = False
        try:
            subprocess.run(["mount", "-o", "bind,ro", "/", self.buildroot], check=True)
            self.tree_mounted = True
            subprocess.run(["mount", "-t", "tmpfs", "tmpfs", self.tree], check=True)
            self.buildroot_mounted = True
        except subprocess.CalledProcessError:
            self.unmount()
            raise

        # systemd-nspawn silently removes some characters when choosing a
        # machine name from the directory name. The only one relevant for
        # us is '_', because all other characters used by
        # TemporaryDirectory() are allowed. Replace it with 'L's
        # (TemporaryDirectory() only uses lower-case characters)
        self.machine_name = os.path.basename(self.buildroot).replace("_", "L")

    def unmount(self):
        if self.tree:
            if self.tree_mounted:
                subprocess.run(["umount", "--lazy", self.tree], check=True)
            os.rmdir(self.tree)
            self.tree = None
        if self.buildroot:
            if self.buildroot_mounted:
                subprocess.run(["umount", "--lazy", self.buildroot], check=True)
            os.rmdir(self.buildroot)
            self.buildroot = None

    def run(self, argv, binds=[], readonly_binds=[], *args, **kwargs):
        return subprocess.run([
            "systemd-nspawn",
            "--quiet",
            "--as-pid2",
            "--link-journal=no",
            "--volatile=yes",
            f"--machine={self.machine_name}",
            f"--directory={self.buildroot}",
            f"--bind={self.tree}:/tmp/tree",
            *[f"--bind={src}:{dest}" for src, dest in binds],
            *[f"--bind-ro={src}:{dest}" for src, dest in readonly_binds]
        ] + argv, *args, **kwargs)

    def run_stage(self, stage, options={}, input_dir=None, sit=False):
        options = {
            **options,
            "tree": "/tmp/tree",
            "input_dir": None
        }

        robinds = [
            (f"{libdir}/run-stage", "/tmp/run-stage"),
            (f"{libdir}/stages/{stage}", "/tmp/stage"),
            ("/etc/pki", "/etc/pki")
        ]
        if input_dir:
            options["input_dir"] = "/tmp/input"
            robinds.append((input_dir, "/tmp/input"))

        argv = ["/tmp/run-stage"]
        if sit:
            argv.append("--sit")
        argv.append("/tmp/stage")

        try:
            self.run(argv, readonly_binds=robinds, input=json.dumps(options), encoding="utf-8", check=True)
        except subprocess.CalledProcessError as error:
            raise StageFailed(stage, error.returncode)

    def run_assembler(self, name, options, output_dir=None, sit=False):
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        options = {
            **options,
            "tree": "/tmp/tree",
            "input_dir": None
        }

        robinds = [
            (f"{libdir}/run-stage", "/tmp/run-stage"),
            (f"{libdir}/stages/{name}", "/tmp/stage"),
            ("/etc/pki", "/etc/pki")
        ]

        binds = []
        if output_dir:
            options["output_dir"] = "/tmp/output"
            binds.append((output_dir, "/tmp/output"))

        argv = ["/tmp/run-stage"]
        if sit:
            argv.append("--sit")
        argv.append("/tmp/stage")

        try:
            self.run(argv, binds=binds, readonly_binds=robinds, input=json.dumps(options), encoding="utf-8", check=True)
        except subprocess.CalledProcessError as error:
            raise StageFailed(stage, error.returncode)

    def __del__(self):
        self.unmount()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.unmount()
