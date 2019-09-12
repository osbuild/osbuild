import contextlib
import os
import re
import subprocess
import sys
import tempfile


class NoFreeNbdDeviceError(Exception):
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
        print(device)
        returncode = subprocess.run(["qemu-nbd", "--connect", device, "--read-only", image]).returncode

        if returncode == 0:
            try:
                yield device
            finally:
                subprocess.run(["qemu-nbd", "--disconnect", device], check=True)
                return

    # raise an exception if exporting with every available nbd device fails
    raise NoFreeNbdDeviceError


@contextlib.contextmanager
def mount_image(image):
    with tempfile.TemporaryDirectory() as tmp, export_image_using_nbd(image) as nbd_device:
        # TODO: support more partitions than only the first one
        nbd_partition = nbd_device + "p1"
        subprocess.run(["mount", "-o", "ro", nbd_partition, tmp], check=True)
        try:
            yield tmp
        finally:
            subprocess.run(["umount", "--lazy", tmp], check=True)


# guestmount code:
# @contextlib.contextmanager
# def open_image(image):
#     with tempfile.TemporaryDirectory() as tmp:
#         subprocess.run(["guestmount", "-a", image, "-i", "--ro", tmp], check=True)
#         try:
#             yield tmp
#         finally:
#             subprocess.run(["guestunmount", tmp], check=True)


def main():
    if len(sys.argv) != 2:
        print("You need to specify image as the first argument!", file=sys.stderr)
        sys.exit(1)

    image = sys.argv[1]

    if not os.path.isfile(image):
        print("Provided file doesn't exist!", file=sys.stderr)
        sys.exit(2)

    with mount_image(image) as root:
        with open(os.path.join(root, "/etc/fedora-release")) as f:
            print(f.read())


if __name__ == "__main__":
    main()
