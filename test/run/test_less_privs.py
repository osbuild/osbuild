import os
import random
import string
import subprocess
import warnings
from contextlib import contextmanager
from pathlib import Path

import pytest


def has_selinux_lsm():
    lsms = Path("/sys/kernel/security/lsm").read_text("utf8").split(",")
    return "selinux" in lsms


@contextmanager
def osbuild_container():
    container_tag = "osbuild-test-" + "".join(random.choices(string.digits, k=12))
    cntfile_path = Path(__file__).parent / "../../Containerfile"
    subprocess.check_call([
        "podman", "build",
        "--cache-ttl=0",
        "-t", container_tag,
        "-f", cntfile_path], encoding="utf8")
    yield container_tag
    subprocess.check_call(["podman", "rmi", container_tag])


@pytest.mark.skipif(os.getuid() == 0, reason="must run as user")
def test_osbuild_rootless_container_with_less_privs_pr2187(tmp_path):
    # the container manifest does not require loopback mounts so we
    # use it for this test
    manifest_in_path = Path(__file__).parent / "../data/manifests/fedora-container.json"
    manifest_out_path = manifest_in_path

    # On a non-selinux system (like Ubuntu in the GH runners) labeling
    # in a user-namespace will always error with EPERM. This works
    # fine however on a selinux system even if selinux is disabled via
    # SELINUX=disabled in /etc/selinux/config (i.e. selinux getting
    # initialized in the kernel config is enough).
    # See https://github.com/torvalds/linux/blob/v6.16/security/selinux/hooks.c#L3293
    if not has_selinux_lsm():
        warnings.warn("no selinux detected, applying workaround")
        manifest_no_selinux = manifest_in_path.read_text("utf8").replace(
            "org.osbuild.selinux", "org.osbuild.noop")
        manifest_out_path = tmp_path / "manifest_no_selinux.json"
        manifest_out_path.write_text(manifest_no_selinux, "utf8")

    # build container
    with osbuild_container() as cnt_tag:
        subprocess.check_call([
            "podman", "run", "--rm",
            # we need this for bind mounts
            "--cap-add=SYS_ADMIN",
            # bubble wrap needs this curently
            "--cap-add=NET_ADMIN",
            # tweak selinux
            "--security-opt", "label=disable",
            # volumes
            "-v", f"{manifest_out_path}:/manifest.json",
            "-v", f"{tmp_path}:/output",
            cnt_tag,
            "/manifest.json",
            "--export", "container",
            "--output-directory", "/output",
        ])
    assert (tmp_path / "container" / "fedora-container.tar").exists()


@pytest.mark.skipif(os.getuid() != 0, reason="must run as root")
def test_osbuild_rootful_with_less_privs_pr2187(tmp_path):
    manifest_path = Path(__file__).parent / "../data/manifests/fedora-boot.json"

    # build container
    with osbuild_container() as cnt_tag:
        subprocess.check_call([
            "podman", "run", "--rm",
            # we need this for bind mounts
            "--cap-add=SYS_ADMIN",
            # bubble wrap needs this curently
            "--cap-add=NET_ADMIN",
            # tweak selinux
            "--security-opt", "label=disable",
            # pass in loop support, ideal to have loop devices in the
            # container, but still less than all of --privileged
            "--device", "/dev/loop-control",
            "--device-cgroup-rule", "b 7:* rwm",
            # volumes
            "-v", f"{manifest_path}:/manifest.json",
            "-v", f"{tmp_path}:/output",
            # so that the loop-control devices are available
            "-v", "/dev:/dev",
            cnt_tag,
            "/manifest.json",
            "--export", "image",
            "--output-directory", "/output",
        ])
    assert (tmp_path / "image" / "disk.img").exists()
