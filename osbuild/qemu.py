import gzip
import importlib.util
import io
import json
import lzma
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from osbuild.util import host, linux


def find_kernel_dir(tree):
    modules_dir = Path(tree) / "usr" / "lib" / "modules"

    if not modules_dir.exists() or not modules_dir.is_dir():
        return None, None

    try:
        subdirs = [d for d in modules_dir.iterdir() if d.is_dir()]
    except PermissionError:
        return None, None

    for subdir in sorted(subdirs):
        vmlinuz_path = subdir / "vmlinuz"
        if vmlinuz_path.is_file():
            return modules_dir / subdir.name

    raise ValueError("No valid kernel directory found in /usr/lib/modules")


def get_module_dependencies(module_path):
    result = subprocess.run(
        ["modinfo", "-F", "depends", str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []

    depends = result.stdout.strip()
    if not depends:
        return []

    deps = [dep.strip() for dep in depends.split(",") if dep.strip()]
    return deps


class InitrdBuilder:
    def __init__(self, source_modules):
        self.tmpdir = None
        self.root = None
        self.source_modules = source_modules

        self.copied_modules = set()
        self.module_counter = 0

    def __enter__(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.tmpdir.cleanup()

    def mkdir(self, path):
        (self.root / path).mkdir(parents=True)

    def add_file(self, src, dest):
        shutil.copy2(src, self.root / dest)

    def add_binary(self, src, dest):
        self.add_file(src, dest)
        (self.root / dest).chmod(0o755)

    def find_module(self, module_name):
        patterns = [
            f"{module_name}.ko",
            f"{module_name}.ko.xz",
            f"{module_name}.ko.zst",
            f"{module_name}.ko.gz",
        ]

        for pattern in patterns:
            matches = list(self.source_modules.rglob(pattern))
            if matches:
                return matches[0]

        return None

    def decompress_module(self, module_path, dest_file):
        """Decompress a module file to destination."""
        module_name = module_path.name

        if module_name.endswith(".ko.xz"):
            with lzma.open(module_path, "rb") as f_in:
                with open(dest_file, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
        elif module_name.endswith(".ko.zst"):
            subprocess.run(
                ["zstd", "-dc", str(module_path)],
                stdout=open(dest_file, "wb"),
                check=True,
            )
        elif module_name.endswith(".ko.gz"):
            with gzip.open(module_path, "rb") as f_in:
                with open(dest_file, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copy2(module_path, dest_file)

    def copy_module(self, module_name):
        if module_name in self.copied_modules:
            return
        self.copied_modules.add(module_name)

        module_path = self.find_module(module_name)
        if not module_path:
            print(f"Warning: {module_name} module not found in {self.source_modules}", file=sys.stderr)
            return

        dependencies = get_module_dependencies(module_path)
        for dep in dependencies:
            self.copy_module(dep)

        modules_dir = self.root / "usr/lib/modules"

        if self.module_counter == 0:
            modules_dir.mkdir(parents=True)
        self.module_counter += 1

        prefix = f"{self.module_counter:03d}"
        dest_file = modules_dir / f"{prefix}-{module_name}.ko"

        self.decompress_module(module_path, dest_file)

    def write(self, dest):
        with open(dest, "wb") as f_out:
            result = subprocess.run(
                ["find", ".", "-print0"],
                cwd=self.root,
                stdout=subprocess.PIPE,
                check=True,
            )
            subprocess.run(
                ["cpio", "--null", "--create", "--format=newc", "--quiet"],
                cwd=self.root,
                input=result.stdout,
                stdout=f_out,
                check=True,
            )


def create_initrd(libdir, rootfs_dir, dest, extra_modules=None):
    kernel_dir = find_kernel_dir(rootfs_dir)

    with InitrdBuilder(kernel_dir) as builder:
        builder.mkdir("bin")
        builder.add_binary(Path(libdir) / "initrd/initrd", "init")
        builder.copy_module("virtiofs")
        if extra_modules:
            for module in extra_modules:
                print(f"Copying additional module: {module}")
                builder.copy_module(module)

        builder.write(dest)


def find_virtiofsd():
    binary_name = "virtiofsd"
    bin_dirs = ["/usr/libexec", "/usr/lib", "/usr/lib/qemu"]
    if "PATH" in os.environ:
        bin_dirs += os.environ["PATH"].split(":")

    for d in bin_dirs:
        p = os.path.join(d, binary_name)
        if os.path.isfile(p):
            return p

    raise RuntimeError("Can't find virtiofsd binary")


class Virtiofsd:
    def __init__(
        self,
        share_dir: str,
        socket_path: str,
        readonly: bool,
    ):
        self.share_dir = share_dir
        self.cmd = [
            find_virtiofsd(),
            "--socket-path=" + socket_path,
            "--shared-dir", share_dir,
            "--cache", "always",
            "--sandbox=none",
            "--xattr",
            "--security-label",
            "--log-level=off",
        ]
        if readonly:
            self.cmd += ["--readonly"]
        self._proc: Optional[subprocess.Popen] = None

    def start(self) -> int:
        if self._proc is not None:
            return self._proc.pid

        self._proc = subprocess.Popen(
            self.cmd,
            text=False,
            close_fds=True,
        )

        return self._proc.pid

    def stop(self) -> None:
        p = self._proc
        if not p:
            return

        try:
            p.terminate()
        except ProcessLookupError:
            self._proc = None
            return

        # Wait a bit for graceful exit
        try:
            p.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            try:
                p.kill()
            except ProcessLookupError:
                pass
            try:
                p.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass

        self._proc = None

    # Context manager
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        return False


def find_qemu(arch):
    binary_names = [f"qemu-system-{arch}", "qemu-kvm"]

    for binary_name in binary_names:
        qemu_bin_dirs = ["/usr/bin", "/usr/libexec"]
        if "PATH" in os.environ:
            qemu_bin_dirs += os.environ["PATH"].split(":")

        for d in qemu_bin_dirs:
            p = os.path.join(d, binary_name)
            if os.path.isfile(p):
                return p

    raise RuntimeError("Can't find qemu binary")


def qemu_available_accels(qemu):
    info = subprocess.check_output([qemu, "-accel", "help"]).decode('utf-8').splitlines()
    # First line is header, skip it
    return info[1:]


def set_pdeathsig():
    PR_SET_PDEATHSIG = 1
    libc = linux.Libc.default()
    libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM)


class Qemu:
    def __init__(
        self,
        mem: str,
        rootfs_path: str,
        libdir_path: str,
        serial_stdout: bool = False,
    ) -> None:
        self._pid: Optional[int] = None

        self._tmpdir = tempfile.TemporaryDirectory(prefix="osbuild-qemu-")
        self.pidfile = os.path.join(self._tmpdir.name, "qemu.pid")
        self.serials: Dict[str, str] = {}
        self.virtiofs: Dict[str, Tuple[str, Virtiofsd]] = {}
        self._proc: Optional[subprocess.Popen] = None

        kerneldir = find_kernel_dir(rootfs_path)
        kernel_path = kerneldir / "vmlinuz"

        initrd_path = Path(self._tmpdir.name) / "initrd"
        create_initrd(libdir_path, rootfs_path, initrd_path)

        self.qmp_path = Path(self._tmpdir.name) / "qmp.sock"

        arch = platform.machine()
        qemu_bin = find_qemu(arch)
        qemu_accels = qemu_available_accels(qemu_bin)

        self.cmd = [
            qemu_bin,
            "-qmp", f"unix:{self.qmp_path},server=on,wait=off",
            "-display",
            "none",
            "-m",
            mem,
            "-cpu", "host",
            # This is needed for virtiofs, and size must match -m
            "-object",
            f"memory-backend-memfd,id=mem0,size={mem},share=on",
            "-numa",
            "node,memdev=mem0",
        ]
        self._id_counter = 0

        console = "ttyS0"
        if arch == "aarch64":
            console = "ttyAMA0"
            self.cmd += ["-machine", "virt"]
        elif arch == "x86_64":
            self.cmd += ["-machine", "q35"]

        if serial_stdout:
            self.cmd += ["-serial", "file:/dev/stdout"]

        if "kvm" in qemu_accels and os.path.exists("/dev/kvm"):
            self.cmd += ["-enable-kvm"]

        init = "/run/mnt/mnt0/osbuild/vm.py"
        cmdline = f"console={console} quiet selinux=1 enforcing=0 rootfstype=virtiofs root=rootfs ro mount=mnt0 init={init}"

        # vm.py will add its parent to the search path to find the "osbuild" module, so
        # mount the directory with the osbuild directory at /mnt and run /mnt/osbuild/vm.py
        spec = importlib.util.find_spec("osbuild")
        assert spec is not None and spec.origin is not None
        modpath = os.path.dirname(spec.origin)  # $some_python_path/osbuild
        modpath = os.path.dirname(modpath)  # $some_python_path

        self.add_kernel(str(kernel_path), str(initrd_path), cmdline)
        self.add_virtio_serial("ipc.0")
        self.add_virtiofs(rootfs_path, "rootfs", readonly=True)
        self.add_virtiofs(modpath, "mnt0", readonly=True)
        self.add_virtiofs(libdir_path, "libdir", readonly=True)
        try:
            container_storage_conf = host.get_container_storage()
            container_storage = container_storage_conf["storage"]["graphroot"]
            if Path(container_storage).is_dir():
                self.add_virtiofs(container_storage, "containers", readonly=True)
        except FileNotFoundError:
            pass

        self.ipc = None

    def add_arguments(self, args: List[str]) -> None:
        self.cmd += args

    def add_kernel(self, kernel_path: str, initrd_path: str, commandline: str):
        self.add_arguments(
            ["-kernel", kernel_path, "-initrd", initrd_path, "-append", commandline]
        )

    def add_virtio_serial(self, name):
        if name in self.serials:
            raise RuntimeError(f"Virtio serial name {name} already used")
        socket_path = os.path.join(self._tmpdir.name, "serial-" + name + ".sock")
        self.serials[name] = socket_path
        char = self._alloc_chardev()
        self.add_arguments(
            [
                "-device",
                "virtio-serial",
                "-chardev",
                f"socket,path={socket_path},server=on,wait=off,id={char}",
                "-device",
                f"virtserialport,chardev={char},name={name}",
            ]
        )

    def connect_virtio_serial(self, name):
        if name not in self.serials:
            raise RuntimeError(f"Virtio serial name {name} doesn't exist")

        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(self.serials[name])
        raw = client.makefile("rwb", buffering=0)
        txt = io.TextIOWrapper(raw, encoding="utf-8", newline="\n", line_buffering=True)

        return txt

    def ensure_ipc(self):
        if not self.ipc:
            self.ipc = self.connect_virtio_serial("ipc.0")

    def send_request(self, obj):
        self.ensure_ipc()
        self.ipc.write(json.dumps(obj, separators=(",", ":")))
        self.ipc.write("\n")
        self.ipc.flush()

    def read_response(self):
        line = self.ipc.readline()
        return json.loads(line)

    def add_virtiofs(self, share_path, tag, readonly):
        if tag in self.virtiofs:
            raise RuntimeError(f"Virtiofs {tag} already used")
        socket_path = os.path.join(self._tmpdir.name, "virtiofs-" + tag + ".sock")
        virtfsd = Virtiofsd(share_path, socket_path, readonly)
        self.virtiofs[tag] = (socket_path, virtfsd)
        char = self._alloc_chardev()
        self.add_arguments(
            [
                "-chardev",
                f"socket,id={char},path={socket_path}",
                "-device",
                f"vhost-user-fs-pci,queue-size=1024,chardev={char},tag={tag}",
            ]
        )

    def wait_for_qmp(self, timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(str(self.qmp_path))
                s.close()
                return True
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.1)
        return False

    def start(self) -> subprocess.Popen:
        for _path, virtfsd in self.virtiofs.values():
            virtfsd.start()

        # We try to properly clean up the child qemu in stop(), however
        # we also call pdeathsig to enure the child is killed if the parent
        # dies unexpectedly (sigkill for example)
        self._proc = subprocess.Popen(self.cmd, preexec_fn=set_pdeathsig)  # noqa: PLW1509 # pylint: disable=W1509

        # Wait until QMP responds, at that point we know the VM setup
        # is completed.
        if not self.wait_for_qmp():
            self._proc.terminate()
            self._proc = None
            raise RuntimeError("QEMU did not become ready")

        return self._proc

    def stop(self) -> None:
        """Terminate QEMU and clean up the pidfile we own."""
        proc = self._proc
        if proc is None or proc.poll() is not None:
            self.cleanup()
            return

        try:
            proc.terminate()
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()

        self.cleanup()

    def cleanup(self):
        for _path, virtfsd in self.virtiofs.values():
            virtfsd.stop()
        if self._tmpdir:
            self._tmpdir.cleanup()
            self._tmpdir = None

    # Context manager hooks
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        return False

    def __del__(self):
        # Best-effort cleanup if user forgets to exit/stop
        try:
            self.stop()
        except Exception:  # pylint: disable=W0718
            pass

    def monitored_request(self, monitor, opname, **kwargs):
        op = {"op": opname, **kwargs}
        self.send_request(op)
        while True:
            response = self.read_response()
            if "log" in response:
                monitor.log(response["log"])
                continue

            if "ok" not in response:
                raise RuntimeError(f"VM Operation {opname} Unexpected response: {str(response)}")

            ok = response["ok"]
            if not ok:
                errtype = response.get("error")

                if errtype == "handler_exception":
                    raise RuntimeError(
                        f"VM Operation {opname} raised exception: " +
                        response['msg'] + ", trace:\n" + response['trace'])

                raise RuntimeError(f"VM Operation {opname} failed: {response['msg']}")

            return response["r"]

    # --- Internals ------------------------------------------------------------
    def _alloc_chardev(self):
        devid = self._id_counter
        self._id_counter += 1
        return f"char{devid}"

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Exists but not ours
            return True

    @staticmethod
    def _wait_for_exit(pid: int, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not Qemu._is_pid_alive(pid):
                return True
            time.sleep(0.05)
        return False
