import io
import json
import os
import platform
import signal
import socket
import subprocess
import tempfile
import time
from typing import Dict, List, Optional, Tuple


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


def find_qemu():
    arch = platform.machine()
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


class Qemu:
    def __init__(
        self,
        mem: str,
        kernel_path: str,
        initrd_path: str,
        rootfs_path: str,
        libdir_path: str,
        serial_stdout: bool = False,
    ) -> None:
        self._pid: Optional[int] = None

        self._tmpdir = tempfile.TemporaryDirectory(prefix="osbuild-qemu-")
        self.pidfile = os.path.join(self._tmpdir.name, "qemu.pid")
        self.serials: Dict[str, str] = {}
        self.virtiofs: Dict[str, Tuple[str, Virtiofsd]] = {}

        qemu_bin = find_qemu()
        qemu_accels = qemu_available_accels(qemu_bin)

        self.cmd = [
            qemu_bin,
            "-daemonize",
            "-pidfile",
            self.pidfile,
            "-display",
            "none",
            "-m",
            mem,
            # This is needed for virtiofs, and size must match -m
            "-object",
            f"memory-backend-memfd,id=mem0,size={mem},share=on",
            "-numa",
            "node,memdev=mem0",
        ]
        self._id_counter = 0

        if serial_stdout:
            self.cmd += ["-serial", "file:/dev/stdout"]

        if "kvm" in qemu_accels and os.path.exists("/dev/kvm"):
            self.cmd += ["-enable-kvm"]

        init = "/mnt/osbuild/vm.py"
        cmdline = f"console=ttyS0 quiet selinux=1 enforcing=0 rootfstype=virtiofs root=rootfs ro init={init}"
        self.add_kernel(kernel_path, initrd_path, cmdline)
        self.add_virtio_serial("ipc.0")
        self.add_virtiofs(rootfs_path, "rootfs", readonly=True)
        self.add_virtiofs(libdir_path, "mnt0", readonly=True)
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

    def start(self) -> int:
        for _path, virtfsd in self.virtiofs.values():
            virtfsd.start()
        subprocess.run(self.cmd, check=True)
        with open(self.pidfile, "rt", encoding="utf8") as f:
            pid_str = f.read().strip()
        pid = int(pid_str)
        if pid < 1:
            raise RuntimeError("Invalid pid in qemu pidfile")
        self._pid = pid
        return pid

    def stop(self) -> None:
        """Terminate QEMU and clean up the pidfile we own."""
        if self._pid is None:
            self.cleanup()
            return

        try:
            os.kill(self._pid, signal.SIGTERM)
        except ProcessLookupError:
            # Already dead
            self.cleanup()
            return

        if not self._wait_for_exit(self._pid, timeout=5.0):
            try:
                os.kill(self._pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self._wait_for_exit(self._pid, timeout=2.0)

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
