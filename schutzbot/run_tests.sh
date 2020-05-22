#!/bin/bash
set -euxo pipefail

# Get OS details.
source /etc/os-release

# Set up a dnf repository for the RPMs we built via mock.
sudo tee /etc/yum.repos.d/osbuild-mock.repo > /dev/null << EOF
[osbuild-mock]
name=osbuild mock ${BUILD_TAG} ${ID}${VERSION_ID//./}
baseurl=${MOCK_REPO_BASE_URL}/${BUILD_TAG}/${ID}${VERSION_ID//./}
enabled=1
gpgcheck=0
# Default dnf repo priority is 99. Lower number means higher priority.
priority=5
EOF

# Verify that the repository we added is working properly.
sudo dnf list all | grep osbuild-mock

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

# Write a simple hosts file for Ansible.
echo -e "[test_instances]\nlocalhost ansible_connection=local" > hosts.ini

# Get the SHA of osbuild which Jenkins checked out for us.
OSBUILD_VERSION=$(git rev-parse HEAD)

# Deploy osbuild-composer and osbuild using RPMs built in a mock chroot.
# NOTE(mhayden): Jenkins clones the repository and then merges the code from
# the pull request into the repo. This creates a new SHA that exists only in
# Jenkins. We use ${WORKSPACE} below to tell ansible-osbuild to use the clone
# that Jenkins made for testing osbuild.
export ANSIBLE_CONFIG=ansible-osbuild/ansible.cfg
git clone https://github.com/osbuild/ansible-osbuild.git ansible-osbuild
ansible-playbook \
  -i hosts.ini \
  -e install_source=os \
  ansible-osbuild/playbook.yml

# Ensure the testing package is installed.
sudo dnf -y install osbuild-composer-tests

# Run the image tests from osbuild-composer to stress-test osbuild.
git clone https://github.com/osbuild/osbuild-composer
ansible-playbook \
  -e workspace=${WORKSPACE} \
  -e journald_cursor="${JOURNALD_CURSOR}" \
  -e test_type=${TEST_TYPE:-image} \
  -i hosts.ini \
  osbuild-composer/schutzbot/test.yml

# Collect the systemd journal anyway if we made it all the way to the end.
sudo journalctl --after-cursor=${JOURNALD_CURSOR} > systemd-journald.log
