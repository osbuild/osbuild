import contextlib
import logging
import os
import subprocess
import sys
import tempfile
import time
from enum import Enum

EXPECTED_TIME_TO_BOOT = 60  # seconds
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
OBJECTS = os.environ.get("OBJECTS", tempfile.mkdtemp())
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", tempfile.mkdtemp())
OSBUILD = os.environ.get("OSBUILD", "../osbuild")
IMAGE_PATH = os.environ.get("IMAGE_PATH", OUTPUT_DIR + "/base.qcow2")


logging.basicConfig(level=logging.getLevelName(os.environ.get("TESTS_LOGLEVEL", "INFO")))


def run_osbuild(pipeline: str, check=True):
    cmd = [OSBUILD, "--objects", OBJECTS, "-o", OUTPUT_DIR, pipeline]
    logging.info(f"Running osbuild: {cmd}")
    osbuild = subprocess.run(cmd, capture_output=True)
    if osbuild.returncode != 0:
        logging.error(f"{RED}osbuild failed!{RESET}")
        print(f"{BOLD}STDERR{RESET}")
        print(osbuild.stderr.decode())
        print(f"{BOLD}STDOUT{RESET}")
        print(osbuild.stdout.decode())
        if check:
            sys.exit(1)

    return osbuild.returncode


def build_web_server_image():
    run_osbuild("1-create-base.json")
    r = run_osbuild("2-configure-web-server.json", check=False)
    # TODO: remove this workaround once the grub2 stage works on the first try :-)
    if r != 0:
        run_osbuild("2-configure-web-server.json")
    run_osbuild("3-compose-qcow2.json")


class QemuAcceleration(Enum):
    KVMTCG = 0
    HVF = 1
    NONE = 2


def uname() -> str:
    uname = subprocess.run(["uname"], capture_output=True)
    return uname.stdout.decode("utf-8").strip()


def detect_qemu_acceleration() -> QemuAcceleration:
    system = uname()
    if system == "Linux":
        logging.info("Detected Linux (using kvm:tcg)")
        return QemuAcceleration.KVMTCG
    elif system == "Darwin":
        logging.info("Detected macOS (support for hvf is expected)")
        return QemuAcceleration.HVF
    else:
        logging.info("Unknown OS")
        return QemuAcceleration.NONE


@contextlib.contextmanager
def boot_image(path: str):
    qemu_accel_options = {
        QemuAcceleration.KVMTCG: ["-accel", "kvm:tcg"],
        QemuAcceleration.HVF: ["-accel", "hvf"],
        QemuAcceleration.NONE: []
    }
    acceleration = detect_qemu_acceleration()
    network = ["-net", "nic,model=rtl8139", "-net", "user,hostfwd=tcp::8888-:8888"]
    cmd = ["qemu-system-x86_64", "-nographic", "-m", "1024", "-snapshot"] + qemu_accel_options[acceleration]\
          + [path] + network
    logging.info(f"Booting image: {cmd}")
    vm = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        time.sleep(EXPECTED_TIME_TO_BOOT)
        yield None
    finally:
        vm.kill()


def test_web_server():
    cmd = ["curl", "-s", "http://127.0.0.1:8888/index"]
    logging.info(f"Running curl: {cmd}")
    curl = subprocess.run(cmd, capture_output=True)
    logging.info(f"Curl returned: code={curl.returncode}, stdout={curl.stdout.decode()}, stderr={curl.stderr.decode()}")
    assert curl.returncode == 0
    assert curl.stdout.decode("utf-8").strip() == "hello, world!"


if __name__ == '__main__':
    if uname() == "Linux":
        logging.info("Building image")
        build_web_server_image()

    logging.info("Running tests")
    tests = [test_web_server]
    with boot_image(IMAGE_PATH):
        for test in tests:
            try:
                test()
                print(f"{RESET}{BOLD}{test.__name__}: Success{RESET}")
            except AssertionError as e:
                print(f"{RESET}{BOLD}{test.__name__}: {RESET}{RED}Fail{RESET}")
                print(e)
