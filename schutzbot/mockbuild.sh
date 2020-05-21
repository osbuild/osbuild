#!/bin/bash
set -euxo pipefail

# Get OS details.
source /etc/os-release

# Install packages.
sudo dnf -qy install createrepo_c mock
if [[ $ID == 'fedora' ]]; then
    sudo dnf -qy install python3-openstackclient
else
    sudo pip3 -qq install python-openstackclient
fi

# Set variables.
CONTAINER=osbuildci-artifacts
WORKSPACE=${WORKSPACE:-$(pwd)}
MOCK_CONFIG="${ID}-${VERSION_ID%.*}-$(uname -m)"
REPO_DIR=repo/${BUILD_TAG}/${ID}${VERSION_ID//./}

# Clone osbuild-composer.
# TODO(mhayden): After the next osbuild-composer release, use the latest tag
# in the osbuild-composer repository. We can't do that right now because
# osbuild-composer v12 is missing c0ad652db58059e0e99eb7253b6ba85f25bead3f
# which maks RHEL 8's qemu happy with the image tests.
git clone https://github.com/osbuild/osbuild-composer

# Build source RPMs.
make srpm
make -C osbuild-composer srpm

# Fix RHEL 8 mock template.
sudo curl --retry 5 -Lsko /etc/mock/templates/rhel-8.tpl \
    https://gitlab.cee.redhat.com/snippets/2208/raw

# Add fastestmirror to the Fedora template.
sudo sed -i '/^install_weak_deps.*/a fastestmirror=1' \
    /etc/mock/templates/fedora-branched.tpl

# Compile RPMs in a mock chroot
sudo mock -r $MOCK_CONFIG --no-bootstrap-chroot \
    --resultdir $REPO_DIR --with=tests \
    rpmbuild/SRPMS/*.src.rpm osbuild-composer/rpmbuild/SRPMS/*.src.rpm
sudo chown -R $USER ${REPO_DIR}

# Move the logs out of the way.
mv ${REPO_DIR}/*.log $WORKSPACE

# Create a repo of the built RPMs.
createrepo_c ${REPO_DIR}

# Prepare to upload to swift.
mkdir -p ~/.config/openstack
cp $OPENSTACK_CREDS ~/.config/openstack/clouds.yml
export OS_CLOUD=psi

# Upload repository to swift.
pushd repo
    find * -type f -print | xargs openstack object create -f value $CONTAINER
popd