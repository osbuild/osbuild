import os.path
import pathlib
import platform
import shutil
import subprocess
import sys
from contextlib import contextmanager


def ldconfig(*dirs):
    # ld.so.conf must exist, or `ldconfig` throws a warning
    subprocess.run(["touch", "/etc/ld.so.conf"], check=True)

    if len(dirs) > 0:
        with open("/etc/ld.so.conf", "w", encoding="utf8") as f:
            for d in dirs:
                f.write(f"{d}\n")
            f.flush()

    subprocess.run(["ldconfig"], check=True)


def sysusers():
    try:
        subprocess.run(
            ["systemd-sysusers"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        sys.stderr.write(error.stdout)
        sys.exit(1)


@contextmanager
def create_machine_id_if_needed(tree="", keep_empty=False):
    """Create a machine-id with a fake machine id if it does not exist.
       The machine-id file will be delete at context exit unless specified
       with 'keep_empty' variable. In that case an empty machine-id will
       be kept.
    """
    path = pathlib.Path(f"{tree}/etc/machine-id")
    try:
        if not path.exists():
            path.parent.mkdir(mode=0o755, exist_ok=True)
            with path.open(mode="w", encoding="utf8") as f:
                # create a fake machine ID to improve reproducibility
                f.write("ffffffffffffffffffffffffffffffff\n")
                path.chmod(0o444)
        yield
    finally:
        path.unlink()
        if keep_empty:
            path.touch()
            path.chmod(0o444)


def tmpfiles():
    # Allow systemd-tmpfiles to return non-0. Some packages want to create
    # directories owned by users that are not set up with systemd-sysusers.
    subprocess.run(["systemd-tmpfiles", "--create"], check=False)


def nsswitch():
    # the default behavior is fine, but using nss-resolve does not
    # necessarily work in a non-booted container, so make sure that
    # is not configured.
    try:
        os.remove("/etc/nsswitch.conf")
    except FileNotFoundError:
        pass


def python_alternatives():
    """/usr/bin/python3 is a symlink to /etc/alternatives/python3, which points
    to /usr/bin/python3.6 by default. Recreate the link in /etc, so that
    shebang lines in stages and assemblers work.
    """
    os.makedirs("/etc/alternatives", exist_ok=True)
    try:
        os.symlink("/usr/bin/python3.6", "/etc/alternatives/python3")
    except FileExistsError:
        pass


def sequoia():
    # This provides a default set of crypto-policies which is important for
    # re-enabling SHA1 support with rpm (so we can cross-build CentOS-Stream-9
    # images).
    os.makedirs("/etc/crypto-policies", exist_ok=True)
    shutil.copytree(
        "/usr/share/crypto-policies/back-ends/DEFAULT", "/etc/crypto-policies/back-ends"
    )


def quirks():
    # Platform specific quirks
    env = os.environ.copy()

    if platform.machine() == "aarch64":
        # Work around a bug in qemu-img on aarch64 that can lead to qemu-img
        # hangs when more then one coroutine is use (which is the default)
        # See https://bugs.launchpad.net/qemu/+bug/1805256
        env["OSBUILD_QEMU_IMG_COROUTINES"] = "1"

    return env
