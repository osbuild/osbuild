#!/bin/bash
set -euo pipefail

# Colorful output.
function greenprint {
  echo -e "\033[1;32m${1}\033[0m"
}

# function to override template respositores with system repositories which contain rpmrepos snapshots
function template_override {
    sudo dnf -y install jq
    if [[ "$ID" == rhel && ${VERSION_ID%.*} == 10 ]]; then
        TEMPLATE=${ID}-${VERSION_ID%.*}.tpl
        # the distribution-gpg-keys package hasn't been updated yet to include PQC keys
        sudo sed -i "s/gpgcheck=1/gpgcheck=0/" /etc/mock/templates/"$TEMPLATE"
    fi

    if sudo subscription-manager status; then
        greenprint "📋 Running on subscribed RHEL machine, no mock template override done."
        return 0
    fi
    if [[ "$ID" == rhel ]]; then
        TEMPLATE=${ID}-${VERSION_ID%.*}.tpl
        # disable subscription for nightlies
        sudo sed -i "s/config_opts\['redhat_subscription_required'\] = True/config_opts['redhat_subscription_required'] = False/" /etc/mock/templates/"$TEMPLATE"
    elif [[ "$ID" == fedora ]]; then
        TEMPLATE=fedora-branched.tpl
    elif [[ "$ID" == centos ]]; then
        TEMPLATE=${ID}-stream-${VERSION_ID}.tpl
        STREAM=-stream
    fi
    greenprint "📋 Updating $ID-$VERSION_ID mock template with rpmrepo snapshot repositories"
    REPOS=$(jq -r ."\"${ID}${STREAM:-}-${VERSION_ID}\".repos[].file" Schutzfile)
    sudo sed -i '/user_agent/q' /etc/mock/templates/"$TEMPLATE"
    for REPO in $REPOS; do
        sudo cat "$REPO" | sudo tee -a /etc/mock/templates/"$TEMPLATE"
    done
    echo '"""' | sudo tee -a /etc/mock/templates/"$TEMPLATE"
}

# Retry dnf install up to 5 times with exponential backoff time
function dnf_install_with_retry {
    local n=1
    local attempts=5
    local timeout=1
    while true; do
        if sudo dnf install -y "$@"; then
            break
        elif [ $n -lt $attempts ]; then
            ((n++))
            # exponentially increase the timeout
            timeout=$((n ** 2))
            echo "Retrying dnf install in $timeout seconds..."
            sleep "$timeout"
        else
            echo "dnf install failed after $n attempts: aborting" >&2
            return 1
        fi
    done
}

# Get OS and architecture details.
source tools/set-env-variables.sh

# Register RHEL if we are provided with a registration script and intend to do that.
REGISTER="${REGISTER:-'false'}"
if [[ $REGISTER == "true" && -n "${V2_RHN_REGISTRATION_SCRIPT:-}" ]] && ! sudo subscription-manager status; then
    greenprint "🪙 Registering RHEL instance"
    sudo chmod +x "$V2_RHN_REGISTRATION_SCRIPT"
    sudo "$V2_RHN_REGISTRATION_SCRIPT"
fi

# Mock configuration file to use for building RPMs.
MOCK_CONFIG="${ID}-${VERSION_ID%.*}-$(uname -m)"

if [[ $ID == centos ]]; then
    MOCK_CONFIG="centos-stream-${VERSION_ID%.*}-$(uname -m)"
fi

# The commit this script operates on.
COMMIT=$(git rev-parse HEAD)

# Bucket in S3 where our artifacts are uploaded
REPO_BUCKET=osbuild-composer-repos

# Public URL for the S3 bucket with our artifacts.
MOCK_REPO_BASE_URL="http://${REPO_BUCKET}.s3.amazonaws.com"

# Distro version in whose buildroot was the RPM built.
DISTRO_VERSION=${ID}-${VERSION_ID}

if [[ "$ID" == rhel ]] && sudo subscription-manager status; then
  # If this script runs on a subscribed RHEL, the RPMs are actually built
  # using the latest CDN content, therefore rhel-*-cdn is used as the distro
  # version.
  DISTRO_VERSION=rhel-${VERSION_ID%.*}-cdn
fi

# Relative path of the repository – used for constructing both the local and
# remote paths below, so that they're consistent.
REPO_PATH=osbuild/${DISTRO_VERSION}/${ARCH}/${COMMIT}

# Directory to hold the RPMs temporarily before we upload them.
REPO_DIR=repo/${REPO_PATH}

# Full URL to the RPM repository after they are uploaded.
REPO_URL=${MOCK_REPO_BASE_URL}/${REPO_PATH}

# Don't rerun the build if it already exists
if curl --silent --fail --head --output /dev/null "${REPO_URL}/repodata/repomd.xml"; then
  greenprint "🎁 Repository already exists. Exiting."
  exit 0
fi

# Mock and s3cmd is only available in EPEL for RHEL.
if [[ $ID == rhel || $ID == centos ]] && ! rpm -q epel-release; then
    greenprint "📦 Setting up EPEL repository"
    curl -Ls --retry 5 --output /tmp/epel.rpm \
        https://dl.fedoraproject.org/pub/epel/epel-release-latest-${VERSION_ID%.*}.noarch.rpm
    dnf_install_with_retry /tmp/epel.rpm
fi

# NOTE: Version mismatches between the packages we're about to install below
# and the existing openssl-libs installed on the system can cause issues:
#   symbol lookup error: /lib64/librpm_sequoia.so.1: undefined symbol: EVP_PKEY_verify_message_init, version OPENSSL_3.4.0
# Upgrading openssl-libs so it matches the versions of the packages that will be installed.
greenprint "📦 Upgrading openssl-libs"

sudo dnf upgrade -y openssl-libs
# Install requirements for building RPMs in mock.
greenprint "📦 Installing mock requirements"
dnf_install_with_retry createrepo_c make mock mock-core-configs python3-pip rpm-build s3cmd rpmdevtools


# Deal with PQC, see https://github.com/rpm-software-management/distribution-gpg-keys/pull/152/
# 1) Add the Red Hat's PQC key, see Release Key #4, here: https://access.redhat.com/security/team/key
# 2) Always enable using the bootstrap image so we have RPM stack with PQC support
sudo tee /usr/share/distribution-gpg-keys/redhat/RPM-GPG-KEY-redhat10-release <<EOF > /dev/null
-----BEGIN PGP PUBLIC KEY BLOCK-----

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
AAAAAAAAAAAAAAAAAAAAAAAABxAYHiIlLTU=
=apor
-----END PGP PUBLIC KEY BLOCK-----
EOF
sudo tee -a /etc/mock/templates/rhel-10.tpl <<EOF > /dev/null
config_opts['use_bootstrap_image'] = 'True'
EOF

# Print some data.
greenprint "🧬 Using mock config: ${MOCK_CONFIG}"
greenprint "📦 SHA: ${COMMIT}"
greenprint "📤 RPMS will be uploaded to: ${REPO_URL}"

# Build source RPMs.
greenprint "🔧 Building source RPMs."
make srpm

# override template repositories
template_override

greenprint "🎟 Adding user to mock group"
sudo usermod -a -G mock "$(whoami)"

# Compile RPMs in a mock chroot
greenprint "🎁 Building RPMs with mock"
mock -r $MOCK_CONFIG \
    --resultdir $REPO_DIR \
    rpmbuild/SRPMS/*.src.rpm
sudo chown -R $USER ${REPO_DIR}

# Change the ownership of all of our repo files from root to our CI user.
sudo chown -R "$USER" "${REPO_DIR%%/*}"

greenprint "🧹 Remove logs from mock build"
rm "${REPO_DIR}"/*.log

# Create a repo of the built RPMs.
greenprint "⛓️ Creating dnf repository"
createrepo_c "${REPO_DIR}"

# Upload repository to S3.
greenprint "☁ Uploading RPMs to S3"
pushd repo
    s3cmd --acl-public put --recursive . s3://${REPO_BUCKET}/
popd
