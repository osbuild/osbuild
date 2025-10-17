#!/usr/bin/python3

import codecs
import contextlib
import errno
import io
import json
import os
import selectors
import subprocess
import sys
import time
import traceback
from typing import Any, Callable, Dict, Optional

# Ensure we can import osbuild module from the same directory as vm.py
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

# These imports really have to go after the path was modified
# pylint: disable=C0413
from osbuild.objectstore import ObjectStore  # noqa: E402

# pylint: enable=C0413


class SerialConnection:
    def __init__(self, path):
        fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
        raw = io.FileIO(fd, mode="r+b")
        self.txt = io.TextIOWrapper(
            io.BufferedRWPair(raw, raw),
            encoding="utf-8",
            newline="\n",
            line_buffering=True,
            write_through=True,
        )

    def send_line(self, line: str) -> None:
        """Send a line (adds newline automatically)."""
        self.txt.write(line.rstrip("\n") + "\n")
        self.txt.flush()

    def recv_line(self) -> str:
        """Read one line (blocking until newline or timeout)."""
        return self.txt.readline()

    def send_ok(self, **kwargs):
        self.send_response({"ok": True, **kwargs})

    def send_error(self, error_type: str, message: str, **kwargs):
        self.send_response(
            {"ok": False, "error": error_type, "msg": message, **kwargs}
        )

    def send_response(self, obj: Dict[str, Any]) -> None:
        data = json.dumps(obj, separators=(",", ":"))
        self.send_line(data)

    def send_stdio(self, line: str, dest: str) -> None:
        resp = {"stdio": dest, "line": line}
        self.send_response(resp)

    def read_request(self) -> Optional[Dict[str, Any]]:
        line = self.txt.readline()
        if not line:
            return None  # EOF
        return json.loads(line)

    def close(self) -> None:
        self.txt.close()


def serve(
    serial: SerialConnection,
    handlers: Dict[str, Callable[[Dict[str, Any], SerialConnection], Dict[str, Any]]],
) -> None:
    """
    Block forever reading JSON requests from a virtio-serial port and responding.

    Request format:
      {
        "op": "<name>",     # required; picks a handler in `handlers`
        "id": "<optional-id>",     # echoed back so clients can correlate replies
        ... other fields passed to handler ...
      }

    Handler signature:  handler(request_dict) -> response_dict
    The response will include "id" if it was present in the request.

    each message is 1 line of UTF-8 JSON ending with '\n'
    """
    while True:
        try:
            req = serial.read_request()
            if req is None:
                # Peer closed; block until new writer connects, or exit.
                # Sleep a bit to avoid busy loop; reopen if needed.
                time.sleep(0.05)
                continue

            op = req["op"]
            if not isinstance(op, str) or op not in handlers:
                serial.send_error("unknown_op", f"Unsupported operation: {op!r}")
                continue

            try:
                result = handlers[op](req, serial)
                if not isinstance(result, dict):
                    raise TypeError("handler must return a dict")
                if "ok" not in result:
                    result["ok"] = True
                serial.send_response(result)
            except Exception as e:  # pylint: disable=W0718
                serial.send_error("handler_exception", str(e), trace=traceback.format_exc())
        except json.JSONDecodeError as e:
            # Malformed JSON — report and continue
            serial.send_error("invalid_json", str(e))
        except OSError as e:
            if e.errno in (errno.EIO, errno.EPIPE):
                # Writer disappeared; loop will try again
                time.sleep(0.05)
                continue
            raise


def op_ping(req: Dict[str, Any], serial: SerialConnection) -> Dict[str, Any]:
    return {"ok": True, "echo": req.get("payload")}


def op_run(req: Dict[str, Any], serial: SerialConnection) -> Dict[str, Any]:
    cmd = req["cmd"]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        bufsize=0,
        close_fds=True,
    )

    assert proc.stdout is not None
    assert proc.stderr is not None

    os.set_blocking(proc.stdout.fileno(), False)
    os.set_blocking(proc.stderr.fileno(), False)

    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ, data=("STDOUT", "utf-8"))
    sel.register(proc.stderr, selectors.EVENT_READ, data=("STDERR", "utf-8"))

    decoders = {
        proc.stdout.fileno(): codecs.getincrementaldecoder("utf-8")("replace"),
        proc.stderr.fileno(): codecs.getincrementaldecoder("utf-8")("replace"),
    }
    buffers = {proc.stdout.fileno(): "", proc.stderr.fileno(): ""}

    # Keep looping until both streams are closed AND the process has exited.
    # We’ll also break if selector has no more fds registered.
    while True:
        if not sel.get_map():
            proc.poll()
            if proc.returncode is not None:
                break

        for key, _ in sel.select(timeout=0.2):
            stream = key.fileobj
            prefix, encoding = key.data
            fileno = key.fd

            try:
                chunk = os.read(fileno, 8192)
            except BlockingIOError:
                continue

            if not chunk:
                # EOF on this stream: flush any remaining partial line.
                if buffers[fileno]:
                    line = buffers[fileno].rstrip("\n")
                    serial.send_stdio(line, prefix)
                    buffers[fileno] = ""
                sel.unregister(stream)
                continue

            text = decoders[fileno].decode(chunk)
            buffers[fileno] += text

            while True:
                nl = buffers[fileno].find("\n")
                if nl == -1:
                    break
                line = buffers[fileno][:nl]
                serial.send_stdio(line, prefix)
                buffers[fileno] = buffers[fileno][nl + 1:]

        if proc.poll() is not None and not sel.get_map():
            break

    code = proc.wait()

    return {"ok": True, "exit": code}


HANDLERS: Dict[str, Callable[[Dict[str, Any], SerialConnection], Dict[str, Any]]] = {
    "ping": op_ping,
    "run": op_run,
}

load_modules = [
    "virtio_console",
    "loop"
]

if os.path.exists("/etc/selinux/config"):
    subprocess.run(["mount", "-t", "selinuxfs", "none", "/sys/fs/selinux"], check=True)
    subprocess.run(["/usr/sbin/load_policy", "-i"], check=True)

for m in load_modules:
    subprocess.run(["/usr/sbin/modprobe", m], check=False)

mountdir = "/run/osbuildvm"
os.makedirs(mountdir)

mounts = {
    "libdir": "/mnt",
}

subprocess.run(["mount", "-t", "tmpfs", "tmpfs", "/tmp"], check=True)

for subdir in os.listdir("/sys/fs/virtiofs"):
    tagfile = os.path.join("/sys/fs/virtiofs", subdir, "tag")
    with open(tagfile, "r", encoding="utf8") as file:
        tag = file.read().rstrip("\n")
        if tag not in {"rootfs", "mnt0"}:
            dst = os.path.join(mountdir, tag)
            os.makedirs(dst)
            print(f"Mounting virtiofs {tag} at {dst}")
            subprocess.run(["mount", "-t", "virtiofs", tag, dst], check=True)
            mounts[tag] = dst

with contextlib.ExitStack() as cm:

    # We have one single object store for the lifetime of the vm
    store = None
    if "store" in mounts:
        store = ObjectStore(mounts["store"], read_only=True)

        cm.enter_context(store)

    serial_device = "/dev/vport0p1"
    print(f"Handling requests on {serial_device}")
    serial_con = SerialConnection(serial_device)
    try:
        serve(serial_con, HANDLERS)
    finally:
        serial_con.close()
