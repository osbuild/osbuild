
import contextlib
import hashlib
import json
import os
import socket
import shutil
import subprocess
import sys
import tempfile
import osbuild.remoteloop as remoteloop


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
        self.usr_mounted = False
        self.lib_mounted = False
        self.lib64_mounted = False
        self.bin_mounted = False
        self.sbin_mounted = False
        try:
            subprocess.run(["mount", "-t", "tmpfs", "none", self.root], check=True)
            os.mkdir(os.path.join(self.root, "usr"))
            self.mounted = True
            subprocess.run(["mount", "-o", "bind,ro", "/usr", os.path.join(self.root, "usr")], check=True)
            self.usr_mounted = True
            if os.path.isdir("/lib") and not os.path.islink("/lib"):
                os.mkdir(os.path.join(self.root, "lib"))
                subprocess.run(["mount", "-o", "bind,ro", "/lib", os.path.join(self.root, "lib")], check=True)
                self.lib_mounted = True
            if os.path.isdir("/lib64") and not os.path.islink("/lib64"):
                os.mkdir(os.path.join(self.root, "lib64"))
                subprocess.run(["mount", "-o", "bind,ro", "/lib64", os.path.join(self.root, "lib64")], check=True)
                self.lib64_mounted = True
            if os.path.isdir("/bin") and not os.path.islink("/bin"):
                os.mkdir(os.path.join(self.root, "bin"))
                subprocess.run(["mount", "-o", "bind,ro", "/bin", os.path.join(self.root, "bin")], check=True)
                self.bin_mounted = True
            if os.path.isdir("/sbin") and not os.path.islink("/sbin"):
                os.mkdir(os.path.join(self.root, "sbin"))
                subprocess.run(["mount", "-o", "bind,ro", "/sbin", os.path.join(self.root, "sbin")], check=True)
                self.sbin_mounted = True
        except subprocess.CalledProcessError:
            self.unmount()
            raise

    def unmount(self):
        if not self.root:
            return
        if self.sbin_mounted:
            subprocess.run(["umount", "--lazy", os.path.join(self.root, "sbin")], check=True)
            self.sbin_mounted = False
        if self.bin_mounted:
            subprocess.run(["umount", "--lazy", os.path.join(self.root, "bin")], check=True)
            self.bin_mounted = False
        if self.lib64_mounted:
            subprocess.run(["umount", "--lazy", os.path.join(self.root, "lib64")], check=True)
            self.lib64_mounted = False
        if self.lib_mounted:
            subprocess.run(["umount", "--lazy", os.path.join(self.root, "lib")], check=True)
            self.lib_mounted = False
        if self.usr_mounted:
            subprocess.run(["umount", "--lazy", os.path.join(self.root, "usr")], check=True)
            self.usr_mounted = False
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

        return subprocess.run([
            "systemd-nspawn",
            "--register=no",
            "--as-pid2",
            "--link-journal=no",
            "--property=DeviceAllow=block-loop rw",
            f"--directory={self.root}",
            *[f"--bind={b}" for b in (binds or [])],
            *[f"--bind-ro={b}" for b in [f"{self.api}:/run/osbuild/api"] + (readonly_binds or [])],
            ] + argv, **kwargs)

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


def print_header(title, options):
    print()
    print(f"{RESET}{BOLD}{title}{RESET} " + json.dumps(options or {}, indent=2))
    print()


class Stage:
    def __init__(self, name, base, options):
        m = hashlib.sha256()
        m.update(json.dumps(name, sort_keys=True).encode())
        m.update(json.dumps(base, sort_keys=True).encode())
        m.update(json.dumps(options, sort_keys=True).encode())

        self.id = m.hexdigest()
        self.name = name
        self.options = options

    def run(self, tree, interactive=False, check=True, libdir=None):
        with BuildRoot() as buildroot:
            if interactive:
                print_header(f"{self.name}: {self.id}", self.options)

            args = {
                "tree": "/run/osbuild/tree",
                "options": self.options,
            }

            path = "/run/osbuild/lib" if libdir else "/usr/libexec/osbuild"
            r = buildroot.run(
                [f"{path}/osbuild-run", f"{path}/stages/{self.name}"],
                binds=[f"{tree}:/run/osbuild/tree"],
                readonly_binds=[f"{libdir}:{path}"] if libdir else [],
                encoding="utf-8",
                input=json.dumps(args),
                stdout=None if interactive else subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=True
            )
            if check and r.returncode != 0:
                raise StageFailed(self.name, r.returncode, r.stdout)

            return {
                "name": self.name,
                "returncode": r.returncode,
                "output": r.stdout
            }


class Assembler:
    def __init__(self, name, options):
        self.name = name
        self.options = options

    def run(self, tree, output_dir=None, interactive=False, check=True, libdir=None):
        with BuildRoot() as buildroot:
            if interactive:
                print_header(f"Assembling: {self.name}", self.options)

            args = {
                "tree": "/run/osbuild/tree",
                "options": self.options,
            }

            binds = []
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                binds.append(f"{output_dir}:/run/osbuild/output")
                args["output_dir"] = "/run/osbuild/output"

            path = "/run/osbuild/lib" if libdir else "/usr/libexec/osbuild"
            with buildroot.bound_socket("remoteloop") as sock, \
                remoteloop.LoopServer(sock):
                r = buildroot.run(
                    [f"{path}/osbuild-run", f"{path}/assemblers/{self.name}"],
                    binds=binds,
                    readonly_binds=[f"{tree}:/run/osbuild/tree"] + ([f"{libdir}:{path}"] if libdir else []),
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

    def add_stage(self, name, options=None):
        base = self.stages[-1].id if self.stages else self.base
        stage = Stage(name, base, options or {})
        self.stages.append(stage)

    def set_assembler(self, name, options=None):
        self.assembler = Assembler(name, options or {})

    def run(self, output_dir, objects=None, interactive=False, check=True, libdir=None):
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
                r = stage.run(tree, interactive, check, libdir=libdir)
                results["stages"].append(r)
                if r["returncode"] != 0:
                    results["returncode"] = r["returncode"]
                    return results

            if self.assembler:
                r = self.assembler.run(tree, output_dir, interactive, check, libdir=libdir)
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
        pipeline.add_stage(s["name"], s.get("options", {}))

    a = description.get("assembler")
    if a:
        pipeline.set_assembler(a["name"], a.get("options", {}))

    return pipeline
