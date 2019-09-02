import contextlib
import logging
import subprocess
import tempfile
import time

from .config import *


@contextlib.contextmanager
def boot_image(file_name: str):
    acceleration = ["-accel", "kvm:hvf:tcg"]
    network = ["-net", "nic,model=rtl8139", "-net", "user,hostfwd=tcp::8888-:8888"]
    cmd = ["qemu-system-x86_64", "-nographic", "-m", "1024", "-snapshot"] + \
          acceleration + [f"{OUTPUT_DIR}/{file_name}"] + network
    logging.info(f"Booting image: {cmd}")
    vm = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        time.sleep(EXPECTED_TIME_TO_BOOT)
        yield None
    finally:
        vm.kill()


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
    CWD = os.getcwd()
    subprocess.run(["tar", "xf", f"{CWD}/{OUTPUT_DIR}/{file_name}"], cwd=extract_dir, check=True)
    try:
        yield extract_dir
    finally:
        # Clean up?
        pass
