#!/bin/bash
set -euxo pipefail

# Read variables about the OS.
source /etc/os-release

# Create temporary directories for Ansible.
sudo mkdir -vp /opt/ansible_{local,remote}
sudo chmod -R 777 /opt/ansible_{local,remote}

# Restart systemd to work around some Fedora issues in cloud images.
sudo systemctl restart systemd-journald

# Get the current journald cursor.
export JOURNALD_CURSOR=$(sudo journalctl --quiet -n 1 --show-cursor | tail -n 1 | grep -oP 's\=.*$')

# Add a function to preserve the system journal if something goes wrong.
preserve_journal() {
  sudo journalctl --after-cursor=${JOURNALD_CURSOR} > systemd-journald.log
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

# Deploy the software.
git clone https://github.com/osbuild/ansible-osbuild.git ansible-osbuild
ansible-playbook \
  -i hosts.ini \
  -e osbuild_repo=${WORKSPACE} \
  -e osbuild_version=$(git rev-parse HEAD) \
  -e cleanup_composer_directories=yes \
  ansible-osbuild/playbook.yml

# Run the tests only on Fedora 31 for now.
if [[ $NAME == "Fedora" ]] && [[ $VERSION_ID == "31" ]]; then
  ansible-playbook \
    -e workspace=${WORKSPACE} \
    -e journald_cursor="${JOURNALD_CURSOR}" \
    -e test_type=${TEST_TYPE:-image} \
    -i hosts.ini \
    ansible-osbuild/repos/osbuild-composer/jenkins/test.yml
fi

# Collect the systemd journal anyway if we made it all the way to the end.
sudo journalctl --after-cursor=${JOURNALD_CURSOR} > systemd-journald.log
