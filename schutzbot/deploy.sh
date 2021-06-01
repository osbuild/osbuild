#!/bin/bash
set -euxo pipefail

DNF_REPO_BASEURL=http://osbuild-composer-repos.s3-website.us-east-2.amazonaws.com

# The osbuild-composer commit to run reverse-dependency test against.
# Currently: osbuild-composer 29
OSBUILD_COMPOSER_COMMIT=bb235deb6279a0886c0324d61a2511485e6b44f8

# Different path if ran in gitlab CI
extra_repo_path_segment="${EXTRA_REPO_PATH_SEGMENT:-}"

# fallback for gitlab
GIT_COMMIT="${GIT_COMMIT:-${CI_COMMIT_SHA}}"

# Get OS details.
source /etc/os-release
ARCH=$(uname -m)

# Register RHEL if we are provided with a registration script.
if [[ $ID == "rhel" && $VERSION_ID == "8.3" && -n "${RHN_REGISTRATION_SCRIPT:-}" ]] && ! sudo subscription-manager status; then
    sudo chmod +x $RHN_REGISTRATION_SCRIPT
    sudo $RHN_REGISTRATION_SCRIPT
fi

# Add osbuild team ssh keys.
cat schutzbot/team_ssh_keys.txt | tee -a ~/.ssh/authorized_keys > /dev/null

# Set up dnf repositories with the RPMs we want to test
sudo tee /etc/yum.repos.d/osbuild.repo << EOF
[osbuild]
name=osbuild ${GIT_COMMIT}
baseurl=${DNF_REPO_BASEURL}/${extra_repo_path_segment}/osbuild/${ID}-${VERSION_ID}/${ARCH}/${GIT_COMMIT}
enabled=1
gpgcheck=0
# Default dnf repo priority is 99. Lower number means higher priority.
priority=5

[osbuild-composer]
name=osbuild-composer ${OSBUILD_COMPOSER_COMMIT}
baseurl=${DNF_REPO_BASEURL}/osbuild-composer/${ID}-${VERSION_ID}/${ARCH}/${OSBUILD_COMPOSER_COMMIT}
enabled=1
gpgcheck=0
# Give this a slightly lower priority, because we used to have osbuild in this repo as well.
priority=10
EOF

if [[ $ID == rhel ]]; then
    # Set up EPEL repository (for ansible and koji)
    sudo dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm
fi

# Install the Image Builder packages.
# Note: installing only -tests to catch missing dependencies
sudo dnf -y install osbuild-composer-tests

# Set up a directory to hold repository overrides.
sudo mkdir -p /etc/osbuild-composer/repositories
