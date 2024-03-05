#!/bin/bash
set -euxo pipefail

DNF_REPO_BASEURL=http://osbuild-composer-repos.s3.amazonaws.com

# Get OS details.
source /etc/os-release
ARCH=$(uname -m)

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
EOF

# install pckages needed to run tests
sudo dnf install -y osbuild \
                    osbuild-ostree \
                    osbuild-lvm2 \
                    osbuild-luks2 \
                    jq \
                    python3 \
		    unzip
