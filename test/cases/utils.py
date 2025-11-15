"""
Shared utilities for test cases
"""

import os
import subprocess
import sys

OSBUILD_IMAGES_REPO_URL = os.environ.get("OSBUILD_IMAGES_REPO_URL", "https://github.com/osbuild/images.git")


def checkout_images_repo(ref, workdir: os.PathLike) -> str:
    """
    Checkout the 'images' repository at a specific commit and return the path to the directory
    If the repository is already checked-out, switch to the specified commit.
    """
    images_path = os.path.join(workdir, "images")

    if not os.path.exists(images_path):
        print(f"Checking out '{OSBUILD_IMAGES_REPO_URL}' repository at ref '{ref}'")
        try:
            subprocess.check_call(
                ["git", "clone", OSBUILD_IMAGES_REPO_URL, "images"],
                cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )

            subprocess.check_call(
                ["git", "fetch", "--all"],
                cwd=images_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )

            subprocess.check_call(
                ["git", "checkout", ref],
                cwd=images_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError as e:
            print(f"Failed to clone 'images' repository: {e.stdout.decode()}")
            sys.exit(1)
    else:
        print(f"'images' repository is already checked-out at '{images_path}'")

    subprocess.check_call(["git", "checkout", ref], cwd=images_path, stdout=subprocess.DEVNULL)
    return images_path
