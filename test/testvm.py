import argparse
import os
import shlex
import sys

from osbuild.qemu import Qemu

parser = argparse.ArgumentParser(
    description="vm.py tester."
)

parser.add_argument(
    "rootfs",
    type=str,
    help="Path to the root filesystem image or directory",
)
parser.add_argument(
    "--mount",
    metavar="TAG=PATH",
    action="append",
    default=[],
    help="Add a virtiofs mount (can be repeated). Format: TAG=PATH",
)
parser.add_argument(
    "--ro-mount",
    metavar="TAG=PATH",
    action="append",
    default=[],
    help="Add a readonly virtiofs mount (can be repeated). Format: TAG=PATH",
)

args = parser.parse_args()

qemu = Qemu(
    "4G",
    os.path.join(args.rootfs, "vm/vmlinuz"),
    os.path.join(args.rootfs, "vm/initramfs.img"),
    args.rootfs,
    ".",
    serial_stdout=True,
)

for entry in args.ro_mount:
    if "=" not in entry:
        parser.error(f"--mount must be in TAG=PATH format (got: {entry!r})")
    tag, path = entry.split("=", 1)
    tag, path = tag.strip(), path.strip()
    if not tag or not path:
        parser.error(f"--ro-mount entries must have nonempty TAG and PATH (got: {entry!r})")
    if not os.path.exists(path):
        parser.error(f"--ro-mount PATH {path} doesn't exist")
    qemu.add_virtiofs(path, tag, True)

for entry in args.mount:
    if "=" not in entry:
        parser.error(f"--mount must be in TAG=PATH format (got: {entry!r})")
    tag, path = entry.split("=", 1)
    tag, path = tag.strip(), path.strip()
    if not tag or not path:
        parser.error(f"--mount entries must have nonempty TAG and PATH (got: {entry!r})")
    if not os.path.exists(path):
        parser.error(f"--mount PATH {path} doesn't exist")
    qemu.add_virtiofs(path, tag, False)

with qemu:
    while True:
        command = input("vm#: ")
        op = {"op": "run", "cmd": shlex.split(command)}
        qemu.send_request(op)
        while True:
            response = qemu.read_response()
            if "stdio" in response:
                dest = response["stdio"]
                if dest == "STDOUT":
                    print(response["line"])
                else:
                    print(response["line"], file=sys.stderr)
                continue
            if "ok" in response:
                ok = response["ok"]
                if not ok:
                    print(f"*** Error executing command: {response['msg']}")
                else:
                    print("*** exit status: ", response["exit"])
            else:
                print("*** Unexpected response: ", response)
            break
