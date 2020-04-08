#!/bin/bash
set -euxo pipefail

# Ensure Ansible is installed.
sudo dnf -y install ansible

# Clone the latest version of ansible-osbuild.
git clone https://github.com/osbuild/ansible-osbuild.git ansible-osbuild

# Get the current SHA of osbuild.
OSBUILD_VERSION=$(git rev-parse HEAD)

# Run the deployment.
pushd ansible-osbuild
  echo -e "[test_instances]\nlocalhost ansible_connection=local" > hosts.ini
  ansible-playbook \
    -i hosts.ini \
    -e osbuild_repo=${WORKSPACE} \
    -e osbuild_version=${OSBUILD_VERSION} \
    playbook.yml
popd
