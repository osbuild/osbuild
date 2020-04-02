#!/bin/bash
set -euxo pipefail

# Install requirements.
dnf -y install qemu-kvm systemd-container

# Run a boot test.
python3 -m unittest -v test.test_boot
