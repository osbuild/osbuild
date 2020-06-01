#!/bin/bash
set -euxo pipefail

# Colorful output.
function greenprint {
  echo -e "\033[1;32m${1}\033[0m"
}

# Get OS details.
source /etc/os-release

# Set variables.
CONTAINER=osbuildci-artifacts
WORKSPACE=${WORKSPACE:-$(pwd)}
MOCK_CONFIG="${ID}-${VERSION_ID%.*}-$(uname -m)"
POST_MERGE_SHA=$(git rev-parse --short HEAD)
REPO_DIR=repo/${JOB_NAME}/${POST_MERGE_SHA}/${ID}${VERSION_ID//./}
REPO_URL=${MOCK_REPO_BASE_URL}/${JOB_NAME}/${POST_MERGE_SHA}/${ID}${VERSION_ID//./}

# Print some data.
greenprint "🧬 Using mock config: ${MOCK_CONFIG}"
greenprint "📦 Post merge SHA: ${POST_MERGE_SHA}"
greenprint "📤 RPMS will be uploaded to: ${REPO_URL}"

# Clone osbuild-composer.
# TODO(mhayden): After the next osbuild-composer release, use the latest tag
# in the osbuild-composer repository. We can't do that right now because
# osbuild-composer v12 is missing c0ad652db58059e0e99eb7253b6ba85f25bead3f
# which maks RHEL 8's qemu happy with the image tests.
git clone https://github.com/osbuild/osbuild-composer

# Build source RPMs.
greenprint "🔧 Building source RPMs."
make srpm
make -C osbuild-composer srpm

# Fix RHEL 8 mock template for non-subscribed images.
if [[ $NODE_NAME == *rhel8[23]* ]]; then
    greenprint "📋 Updating RHEL 8 mock template for unsubscribed image"
    sudo curl --retry 5 -Lsko /etc/mock/templates/rhel-8.tpl \
        https://gitlab.cee.redhat.com/snippets/2208/raw
fi

# Compile RPMs in a mock chroot
greenprint "🎁 Building RPMs with mock"
sudo mock -r $MOCK_CONFIG --no-bootstrap-chroot \
    --resultdir $REPO_DIR --with=tests \
    rpmbuild/SRPMS/*.src.rpm osbuild-composer/rpmbuild/SRPMS/*.src.rpm
sudo chown -R $USER ${REPO_DIR}

# Move the logs out of the way.
greenprint "🧹 Retaining logs from mock build"
mv ${REPO_DIR}/*.log $WORKSPACE

# Create a repo of the built RPMs.
greenprint "⛓️ Creating dnf repository"
createrepo_c ${REPO_DIR}

# Prepare to upload to swift.
greenprint "🛂 Setting up OpenStack authentication credentials"
mkdir -p ~/.config/openstack
cp $OPENSTACK_CREDS ~/.config/openstack/clouds.yml
export OS_CLOUD=psi

# Upload repository to swift.
greenprint "☁ Uploading RPMs to OpenStack object storage"
pushd repo
    find * -type f -print | xargs openstack object create -f value $CONTAINER
popd

# Create a repository file.
greenprint "📜 Generating dnf repository file"
tee osbuild-mock.repo << EOF
[osbuild-mock]
name=osbuild mock ${JOB_NAME}-${POST_MERGE_SHA} ${ID}${VERSION_ID//./}
baseurl=${REPO_URL}
enabled=1
gpgcheck=0
# Default dnf repo priority is 99. Lower number means higher priority.
priority=5
EOF
