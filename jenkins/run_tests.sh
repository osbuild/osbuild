#!/bin/bash
set -euxo pipefail

# Restart systemd to work around some Fedora issues in cloud images.
systemctl restart systemd-journald

# Get the current journald cursor.
export JOURNALD_CURSOR=$(journalctl --quiet -n 1 --show-cursor | tail -n 1 | grep -oP 's\=.*$')

# Add a function to preserve the system journal if something goes wrong.
preserve_journal() {
  journalctl --after-cursor=${JOURNALD_CURSOR} > systemd-journald.log
  exit 1
}
trap "preserve_journal" ERR

# Ensure Ansible is installed.
if ! rpm -q ansible; then
  sudo dnf -y install ansible
fi

# Write a simple hosts file for Ansible.
echo -e "[test_instances]\nlocalhost ansible_connection=local" > hosts.ini

# Set Ansible's config file location.
export ANSIBLE_CONFIG=ansible-osbuild/ansible.cfg

# Clone the latest version of ansible-osbuild.

# Get the current SHA of osbuild.
OSBUILD_VERSION=$(git rev-parse HEAD)

# Run the deployment.
git clone https://github.com/osbuild/ansible-osbuild.git ansible-osbuild
ansible-playbook \
  -i hosts.ini \
  -e osbuild_repo=${WORKSPACE} \
  -e osbuild_version=$(git rev-parse HEAD) \
  ansible-osbuild/playbook.yml

# Collect the systemd journal anyway if we made it all the way to the end.
journalctl --after-cursor=${JOURNALD_CURSOR} > systemd-journald.log