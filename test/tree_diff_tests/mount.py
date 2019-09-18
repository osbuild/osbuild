import contextlib
import os
import re
import subprocess
import tempfile
import time
from enum import Enum

from test.integration_tests.run import extract_image


class ImageType(Enum):
    QCOW2 = 0
    TAR = 1


class NoFreeNbdDeviceError(RuntimeError):
    pass


def get_nbd_devices():
    devices = os.listdir('/dev')
    nbd_re = re.compile(r"nbd\d+$")
    nbd_devices = [os.path.join("/dev", dev) for dev in devices if nbd_re.match(dev)]
    return nbd_devices


@contextlib.contextmanager
def export_image_using_nbd(image):
    devices = get_nbd_devices()
    for device in devices:
        returncode = subprocess.run(["qemu-nbd", "--connect", device, "--read-only", image]).returncode

        if returncode == 0:
            time.sleep(0.1)
            try:
                yield device
            finally:
                subprocess.run(["qemu-nbd", "--disconnect", device], check=True, stdout=subprocess.DEVNULL)
            return

    # raise an exception if exporting with every available nbd device fails
    raise NoFreeNbdDeviceError


@contextlib.contextmanager
def mount_disk_image(image):
    with tempfile.TemporaryDirectory() as tmp, export_image_using_nbd(image) as nbd_device:
        # TODO: support more partitions than only the first one
        nbd_partition = nbd_device + "p1"
        subprocess.run(["mount", "-o", "ro", nbd_partition, tmp], check=True)
        try:
            yield tmp
        finally:
            subprocess.run(["umount", "--lazy", tmp], check=True)


@contextlib.contextmanager
def mount_image(path: str, image_type: ImageType):
    if image_type == ImageType.QCOW2:
        with mount_disk_image(path) as img:
            yield img
    elif image_type == ImageType.TAR:
        with extract_image(path) as img:
            yield img

