import contextlib
import logging
import subprocess
from os import path

from .config import *


def run_image(file_name: str):
    acceleration = ["-accel", "kvm:hvf:tcg"]
    silence = ["-nographic", "-monitor", "none", "-serial", "none"]
    serial = ["-chardev", "stdio,id=stdio", "-device", "virtio-serial", "-device", "virtserialport,chardev=stdio"]
    cmd = ["qemu-system-x86_64", "-m", "1024", "-snapshot"] + \
          acceleration + silence + serial + [f"{OUTPUT_DIR}/{file_name}"]
    logging.info(f"Booting image: {cmd}")
    return subprocess.run(cmd, capture_output=True, timeout=EXPECTED_TIME_TO_BOOT, encoding="utf-8", check=True)


@contextlib.contextmanager
def extract_image(file_name: str):
    extract_dir = tempfile.mkdtemp(prefix="osbuild-")
    archive = path.join(os.getcwd(), OUTPUT_DIR, file_name)
    subprocess.run(["tar", "xf", archive], cwd=extract_dir, check=True)
    try:
        yield extract_dir
    finally:
        # Clean up?
        pass
