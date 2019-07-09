
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile


__all__ = [
    "Assembler",
    "AssemblerFailed",
    "BuildRoot",
    "Pipeline",
    "Stage"
    "StageFailed",
    "tmpfs"
]


RESET = "\033[0m"
BOLD = "\033[1m"


libdir = os.path.dirname(__file__)
if not os.path.exists(f"{libdir}/stages"):
    libdir = f"{sys.prefix}/lib"


class StageFailed(Exception):
    def __init__(self, stage, returncode, output):
        self.stage = stage
        self.returncode = returncode
        self.output = output


class AssemblerFailed(Exception):
    def __init__(self, assembler, returncode, output):
        self.assembler = assembler
        self.returncode = returncode
        self.output = output


class tmpfs:
    def __init__(self, path="/run/osbuild"):
        self.root = tempfile.mkdtemp(prefix="osbuild-tmpfs-", dir=path)
        self.mounted = False
        try:
            subprocess.run(["mount", "-t", "tmpfs", "-o", "mode=0755", "tmpfs", self.root], check=True)
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

    def run(self, argv, binds=[], readonly_binds=[], **kwargs):
        """Runs a command in the buildroot.

        Its arguments mean the same as those for subprocess.run().
        """
        command = "/run/osbuild/" + os.path.basename(argv[0])
        return subprocess.run([
            "systemd-nspawn",
            "--quiet",
            "--as-pid2",
            "--link-journal=no",
            "--volatile=yes",
            "--property=DeviceAllow=/dev/loop-control rw",
            "--property=DeviceAllow=block-loop rw",
            "--property=DeviceAllow=block-blkext rw",
            f"--machine={self.machine_name}",
            f"--directory={self.root}",
            f"--bind={libdir}/osbuild-run:/run/osbuild/osbuild-run",
            *[f"--bind={b}" for b in binds],
            *[f"--bind-ro={b}" for b in [argv[0] + ":" + command, *readonly_binds]],
            "/run/osbuild/osbuild-run",
            command
            ] + argv[1:], **kwargs
        )

    def __del__(self):
        self.unmount()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.unmount()


def print_header(title, options, machine_name):
    print()
    print(f"{RESET}{BOLD}{title}{RESET} " + json.dumps(options or {}, indent=2))
    print("Inspect with:")
    print(f"\t# nsenter -a --wd=/root -t `machinectl show {machine_name} -p Leader --value`")
    print()


def _get_system_resources_from_etc(resources):
    for r in resources:
        if not r.startswith("/etc"):
            raise ValueError(f"{r} is not a resource in /etc/")
        if ":" in r:
            raise ValueError(f"{r} tries to bind to a different location")
    return resources


class Stage:
    def __init__(self, name, base, options, resources):
        m = hashlib.sha256()
        m.update(json.dumps(name, sort_keys=True).encode())
        m.update(json.dumps(base, sort_keys=True).encode())
        m.update(json.dumps(options, sort_keys=True).encode())
        m.update(json.dumps(resources, sort_keys=True).encode())

        self.id = m.hexdigest()
        self.name = name
        self.options = options
        self.resources = resources

    def run(self, tree, interactive=False):
        with BuildRoot() as buildroot:
            if interactive:
                print_header(f"{self.name}: {self.id}", self.options, buildroot.machine_name)

            args = {
                "tree": "/run/osbuild/tree",
                "options": self.options,
            }

            r = buildroot.run(
                [f"{libdir}/stages/{self.name}"],
                binds=[
                    f"{tree}:/run/osbuild/tree",
                    "/dev:/dev"
                ],
                readonly_binds=_get_system_resources_from_etc(self.resources),
                encoding="utf-8",
                input=json.dumps(args),
                stdout=None if interactive else subprocess.PIPE,
                stderr=subprocess.STDOUT
            )
            if r.returncode != 0:
                raise AssemblerFailed(self.name, r.returncode, r.stdout)

            return {
                "name": self.name,
                "output": r.stdout
            }


class Assembler:
    def __init__(self, name, options, resources):
        self.name = name
        self.options = options
        self.resources = resources

    def run(self, tree, output_dir=None, interactive=False):
        with BuildRoot() as buildroot:
            if interactive:
                print_header(f"Assembling: {self.name}", self.options, buildroot.machine_name)

            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)

            args = {
                "tree": "/run/osbuild/tree",
                "options": self.options,
            }

            binds = ["/dev:/dev"]
            if output_dir:
                binds.append(f"{output_dir}:/run/osbuild/output")
                args["output_dir"] = "/run/osbuild/output"

            r = buildroot.run(
                [f"{libdir}/assemblers/{self.name}"],
                binds=binds,
                readonly_binds=[f"{tree}:/run/osbuild/tree"] + _get_system_resources_from_etc(self.resources),
                encoding="utf-8",
                input=json.dumps(args),
                stdout=None if interactive else subprocess.PIPE,
                stderr=subprocess.STDOUT)
            if r.returncode != 0:
                raise StageFailed(self.name, r.returncode, r.stdout)

            return {
                "name": self.name,
                "output": r.stdout
            }


class Pipeline:
    def __init__(self, pipeline, objects):
        self.base = pipeline.get("base")
        self.stages = pipeline.get("stages", [])
        self.assembler = pipeline.get("assembler")
        self.objects = objects

        os.makedirs(objects, exist_ok=True)

    def run(self, output_dir, interactive=False):
        results = {
            "stages": []
        }
        with tmpfs() as tree:
            base = self.base

            if base:
                input_tree = os.path.join(self.objects, base)
                subprocess.run(["cp", "-a", f"{input_tree}/.", tree], check=True)

            for stage in self.stages:
                name = stage["name"]
                options = stage.get("options", {})
                resources = stage.get("systemResourcesFromEtc", [])
                stage = Stage(name, base, options, resources)
                r = stage.run(tree, interactive)
                results["stages"].append(r)
                base = stage.id

            if self.assembler:
                name = self.assembler["name"]
                options = self.assembler.get("options", {})
                resources = self.assembler.get("systemResourcesFromEtc", [])
                assembler = Assembler(name, options, resources)
                r = assembler.run(tree, output_dir, interactive)
                results["assembler"] = r
            else:
                output_tree = os.path.join(self.objects, base)
                shutil.rmtree(output_tree, ignore_errors=True)
                os.makedirs(output_tree, mode=0o755)
                subprocess.run(["cp", "-a", f"{tree}/.", output_tree], check=True)

        self.results = results
