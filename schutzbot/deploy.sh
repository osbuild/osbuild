#!/bin/bash
set -euxo pipefail

DNF_REPO_BASEURL=http://osbuild-composer-repos.s3.amazonaws.com

# The osbuild-composer commit to run reverse-dependency test against.
# Currently: test: add image test cases for Fedora 34 and 35
OSBUILD_COMPOSER_COMMIT=1401a7a6595f86812008b6bfdacdf7289945a6f3

# Get OS details.
source /etc/os-release
ARCH=$(uname -m)

# Add osbuild team ssh keys.
cat schutzbot/team_ssh_keys.txt | tee -a ~/.ssh/authorized_keys > /dev/null

# Distro version that this script is running on.
DISTRO_VERSION=${ID}-${VERSION_ID}

if [[ "$ID" == rhel ]] && sudo subscription-manager status; then
  # If this script runs on subscribed RHEL, install content built using CDN
  # repositories.
  DISTRO_VERSION=rhel-${VERSION_ID%.*}-cdn
fi

# Set up dnf repositories with the RPMs we want to test
sudo tee /etc/yum.repos.d/osbuild.repo << EOF
[osbuild]
name=osbuild ${CI_COMMIT_SHA}
baseurl=${DNF_REPO_BASEURL}/osbuild/${DISTRO_VERSION}/${ARCH}/${CI_COMMIT_SHA}
enabled=1
gpgcheck=0
# Default dnf repo priority is 99. Lower number means higher priority.
priority=5

[osbuild-composer]
name=osbuild-composer ${OSBUILD_COMPOSER_COMMIT}
baseurl=${DNF_REPO_BASEURL}/osbuild-composer/${DISTRO_VERSION}/${ARCH}/${OSBUILD_COMPOSER_COMMIT}
enabled=1
gpgcheck=0
# Give this a slightly lower priority, because we used to have osbuild in this repo as well.
priority=10
EOF

if [[ $ID == rhel ]] && [[ ${VERSION_ID%.*} == 8 ]]; then
    # Set up EPEL repository (for ansible and koji)
    sudo dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm
elif [[ $ID == rhel ]] && [[ ${VERSION_ID%.*} == 9 ]]; then
    # we have our own small epel for EL9, let's install it

    # install Red Hat certificate, otherwise dnf copr fails
    curl -LO --insecure https://hdn.corp.redhat.com/rhel8-csb/RPMS/noarch/redhat-internal-cert-install-0.1-23.el7.csb.noarch.rpm
    sudo dnf install -y ./redhat-internal-cert-install-0.1-23.el7.csb.noarch.rpm dnf-plugins-core
    sudo dnf copr enable -y copr.devel.redhat.com/osbuild-team/epel-el9 "rhel-9.dev-$ARCH"
fi

# Install the Image Builder packages.
# Note: installing only -tests to catch missing dependencies
sudo dnf -y install osbuild-composer-tests osbuild-tests

# Set up a directory to hold repository overrides.
sudo mkdir -p /etc/osbuild-composer/repositories

# Temp fix until composer gains these dependencies
sudo dnf -y install osbuild-luks2 osbuild-lvm2
