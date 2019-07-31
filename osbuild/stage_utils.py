import subprocess
import os


def run_systemd_firstboot(tree, option, value, delete_file=None):
    # We need to remove the "delete_file" first, because it is created while we install RPM packages. systemd-firstboot
    # expects that if "delete_file" exists it is a user-defined value and does not change it, but the assumption is
    # wrong, because it contains a default value from RPM package.
    # This is (hopefully) a temporary workaround.
    if delete_file is not None:
        try:
            os.remove(f"{tree}/{delete_file}")
            # ^ This will fail once systemd RPM package stops shipping the file
            print(f"{delete_file} already exists. Replacing.")
        except FileNotFoundError:
            pass

    subprocess.run(["systemd-firstboot", f"--root={tree}", f"--{option}={value}"], check=True)

    return 0
