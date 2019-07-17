
import contextlib
import hashlib
import json
import os
import socket
import shutil
import subprocess
import sys
import tempfile


__all__ = [
    "Assembler",
    "AssemblerFailed",
    "BuildRoot",
    "load",
    "Pipeline",
    "Stage",
    "StageFailed",
]


RESET = "\033[0m"
BOLD = "\033[1m"


libdir = os.path.dirname(os.path.dirname(__file__))
if not os.path.exists(f"{libdir}/stages"):
    libdir = f"{sys.prefix}/lib/osbuild"


class StageFailed(Exception):
    def __init__(self, name, returncode, output):
        super(StageFailed, self).__init__()
        self.name = name
        self.returncode = returncode
        self.output = output


class AssemblerFailed(Exception):
    def __init__(self, name, returncode, output):
        super(AssemblerFailed, self).__init__()
        self.name = name
        self.returncode = returncode
        self.output = output


class TmpFs:
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
        self.api = tempfile.mkdtemp(prefix="osbuild-api-", dir=path)
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
        if self.api:
            shutil.rmtree(self.api)
            self.api = None

    def run(self, argv, binds=None, readonly_binds=None, **kwargs):
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
            *[f"--bind={b}" for b in (binds or [])],
            *[f"--bind-ro={b}" for b in [argv[0] + ":" + command,
                                         self.api + ":" + "/run/osbuild/api",
                                         *(readonly_binds or [])]],
            "/run/osbuild/osbuild-run",
            command
            ] + argv[1:], **kwargs)

    @contextlib.contextmanager
    def bound_socket(self, name):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock_path = os.path.join(self.api, name)
        sock.bind(os.path.join(self.api, name))
        try:
            yield sock
        finally:
            os.unlink(sock_path)
            sock.close()

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

    def run(self, tree, interactive=False, check=True):
        with BuildRoot() as buildroot:
            if interactive:
                print_header(f"{self.name}: {self.id}", self.options, buildroot.machine_name)

            args = {
                "tree": "/run/osbuild/tree",
                "options": self.options,
            }

            r = buildroot.run(
                [f"{libdir}/stages/{self.name}"],
                binds=[f"{tree}:/run/osbuild/tree"],
                readonly_binds=_get_system_resources_from_etc(self.resources),
                encoding="utf-8",
                input=json.dumps(args),
                stdout=None if interactive else subprocess.PIPE,
                stderr=subprocess.STDOUT
            )
            if check and r.returncode != 0:
                raise StageFailed(self.name, r.returncode, r.stdout)

            return {
                "name": self.name,
                "returncode": r.returncode,
                "output": r.stdout
            }


class Assembler:
    def __init__(self, name, options, resources):
        self.name = name
        self.options = options
        self.resources = resources

    def run(self, tree, output_dir=None, interactive=False, check=True):
        with BuildRoot() as buildroot:
            if interactive:
                print_header(f"Assembling: {self.name}", self.options, buildroot.machine_name)

            args = {
                "tree": "/run/osbuild/tree",
                "options": self.options,
            }

            binds = ["/dev:/dev"]
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
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
            if check and r.returncode != 0:
                raise AssemblerFailed(self.name, r.returncode, r.stdout)

            return {
                "name": self.name,
                "returncode": r.returncode,
                "output": r.stdout
            }


class Pipeline:
    def __init__(self, base=None):
        self.base = base
        self.stages = []
        self.assembler = None

    def add_stage(self, name, options=None, resources=None):
        base = self.stages[-1].id if self.stages else self.base
        stage = Stage(name, base, options or {}, resources or [])
        self.stages.append(stage)

    def set_assembler(self, name, options=None, resources=None):
        self.assembler = Assembler(name, options or {}, resources or [])

    def run(self, output_dir, objects=None, interactive=False, check=True):
        os.makedirs("/run/osbuild", exist_ok=True)
        if objects:
            os.makedirs(objects, exist_ok=True)
        elif self.base:
            raise ValueError("'objects' argument must be given when pipeline has a 'base'")

        results = {
            "stages": []
        }
        with TmpFs() as tree:
            if self.base:
                subprocess.run(["cp", "-a", f"{objects}/{self.base}/.", tree], check=True)

            for stage in self.stages:
                r = stage.run(tree, interactive, check)
                results["stages"].append(r)
                if r["returncode"] != 0:
                    results["returncode"] = r["returncode"]
                    return results

            if self.assembler:
                r = self.assembler.run(tree, output_dir, interactive, check)
                results["assembler"] = r
                if r["returncode"] != 0:
                    results["returncode"] = r["returncode"]
                    return results

            last = self.stages[-1].id if self.stages else self.base
            if objects and last:
                output_tree = f"{objects}/{last}"
                shutil.rmtree(output_tree, ignore_errors=True)
                os.makedirs(output_tree, mode=0o755)
                subprocess.run(["cp", "-a", f"{tree}/.", output_tree], check=True)

        results["returncode"] = 0
        return results


def load(description):
    pipeline = Pipeline(description.get("base"))

    for s in description.get("stages", []):
        pipeline.add_stage(s["name"], s.get("options", {}), s.get("systemResourcesFromEtc", []))

    a = description.get("assembler")
    if a:
        pipeline.set_assembler(a["name"], a.get("options", {}), a.get("systemResourcesFromEtc", []))

    return pipeline
