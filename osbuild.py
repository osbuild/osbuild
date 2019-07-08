
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile


__all__ = [
    "StageFailed",
    "BuildRoot",
    "Pipeline",
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

    def run(self, argv, binds=[], readonly_binds=[], *args, **kwargs):
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
            *[f"--bind-ro={b}" for b in readonly_binds],
            "/run/osbuild/osbuild-run",
        ] + argv, *args, **kwargs)

    def _get_system_resources_from_etc(self, resources):
        for r in resources:
            if not r.startswith("/etc"):
                raise ValueError(f"{r} is not a resource in /etc/")
            if ":" in r:
                raise ValueError(f"{r} tries to bind to a different location")
        return resources

    def run_stage(self, stage, tree, interactive=False):
        name = stage["name"]
        resources = stage.get("systemResourcesFromEtc", [])
        args = {
            "tree": "/run/osbuild/tree",
            "options": stage.get("options", {})
        }

        robinds = [f"{libdir}/stages/{name}:/run/osbuild/{name}"]
        robinds.extend(self._get_system_resources_from_etc(resources))

        binds = [f"{tree}:/run/osbuild/tree", "/dev:/dev"]

        try:
            r = self.run([f"/run/osbuild/{name}"],
                binds=binds,
                readonly_binds=robinds,
                input=json.dumps(args),
                encoding="utf-8",
                stdout=subprocess.PIPE if not interactive else None,
                stderr=subprocess.STDOUT if not interactive else None,
                check=True)
        except subprocess.CalledProcessError as error:
            raise StageFailed(name, error.returncode, error.stdout)

        return {
            "name": name,
            "output": r.stdout
        }

    def run_assembler(self, assembler, tree, output_dir=None, interactive=False):
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        name = assembler["name"]
        resources = assembler.get("systemResourcesFromEtc", [])
        args = {
            "tree": "/run/osbuild/tree",
            "options": assembler.get("options", {}),
        }
        robinds = [
            f"{tree}:/run/osbuild/tree",
            f"{libdir}/assemblers/{name}:/run/osbuild/{name}"
        ]
        robinds.extend(self._get_system_resources_from_etc(resource))
        binds = ["/dev:/dev"]

        if output_dir:
            binds.append(f"{output_dir}:/run/osbuild/output")
            args["output_dir"] = "/run/osbuild/output"

        try:
            r = self.run([f"/run/osbuild/{name}"],
                binds=binds,
                readonly_binds=robinds,
                input=json.dumps(args),
                encoding="utf-8",
                stdout=subprocess.PIPE if not interactive else None,
                stderr=subprocess.STDOUT if not interactive else None,
                check=True)
        except subprocess.CalledProcessError as error:
            raise StageFailed(name, error.returncode, error.stdout)

        return {
            "name": name,
            "output": r.stdout
        }

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

class Pipeline:
    def __init__(self, pipeline, objects):
        m = hashlib.sha256()
        m.update(json.dumps(pipeline, sort_keys=True).encode())

        self.id = m.hexdigest()
        self.base = pipeline.get("base")
        self.stages = pipeline.get("stages", [])
        self.assembler = pipeline.get("assembler")
        self.objects = objects

        os.makedirs(objects, exist_ok=True)

    def run(self, output_dir, interactive=False):
        results = {
            "stages": []
        }
        with BuildRoot() as buildroot, tmpfs() as tree:
            if self.base:
                input_tree = os.path.join(self.objects, self.base)
                subprocess.run(["cp", "-a", f"{input_tree}/.", tree], check=True)

            for i, stage in enumerate(self.stages, start=1):
                name = stage["name"]
                options = stage.get("options", {})
                if interactive:
                    print_header(f"{i}. {name}", options, buildroot.machine_name)
                r = buildroot.run_stage(stage, tree, interactive)
                results["stages"].append(r)

            if self.assembler:
                name = self.assembler["name"]
                options = self.assembler.get("options", {})
                if interactive:
                    print_header(f"Assembling: {name}", options, buildroot.machine_name)
                r = buildroot.run_assembler(self.assembler, tree, output_dir, interactive)
                results["assembler"] = r
            else:
                output_tree = os.path.join(self.objects, self.id)
                shutil.rmtree(output_tree, ignore_errors=True)
                os.makedirs(output_tree, mode=0o755)
                subprocess.run(["cp", "-a", f"{tree}/.", output_tree], check=True)

        self.results = results
