#!/bin/bash
set -euo pipefail

# Colorful output.
function greenprint {
  echo -e "\033[1;32m${1}\033[0m"
}

# function to override template respositores with system repositories which contain rpmrepos snapshots
function template_override {
    sudo dnf -y install jq
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
# TODO: Adjust this condition, once EPEL-10 is enabled
if [[ ($ID == rhel || $ID == centos) && ${VERSION_ID%.*} -lt 10 ]] && ! rpm -q epel-release; then
    greenprint "📦 Setting up EPEL repository"
    curl -Ls --retry 5 --output /tmp/epel.rpm \
        https://dl.fedoraproject.org/pub/epel/epel-release-latest-${VERSION_ID%.*}.noarch.rpm
    dnf_install_with_retry /tmp/epel.rpm
fi

# TODO: Remove this workaround, once EPEL-10 is enabled
if [[ ($ID == rhel || $ID == centos) && ${VERSION_ID%.*} == 10 ]]; then
    sudo dnf copr enable -y @osbuild/centpkg "centos-stream-10-$(uname -m)"
fi

# Install requirements for building RPMs in mock.
greenprint "📦 Installing mock requirements"
dnf_install_with_retry createrepo_c make mock python3-pip rpm-build s3cmd

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
    AWS_ACCESS_KEY_ID="$V2_AWS_ACCESS_KEY_ID" \
    AWS_SECRET_ACCESS_KEY="$V2_AWS_SECRET_ACCESS_KEY" \
    s3cmd --acl-public put --recursive . s3://${REPO_BUCKET}/
popd
