#!/bin/bash
set -euxo pipefail
# Get OS details.
source /etc/os-release
ARCH=$(uname -m)
DISTRO_CODE="${DISTRO_CODE:-${ID}-${VERSION_ID}}"
# get manifest-db at the version specified for this arch+distro
MANIFEST_DB_COMMIT=$(cat Schutzfile | jq -r '.global.dependencies."manifest-db".commit')
MANIFEST_DB_REPO="https://github.com/osbuild/manifest-db"
git clone "$MANIFEST_DB_REPO" manifest-db
cd manifest-db
git checkout --force "$MANIFEST_DB_COMMIT"

# set the maximum cache size to unlimited
echo "{}" | sudo osbuild --store /var/lib/osbuild/store --cache-max-size unlimited -

IFS='/' read -r -a array <<< $1

sudo dnf install -y osbuild-tools

# run the tests from the manifest-db for this arch+distro
echo "Running the osbuild-image-test for arch $ARCH and ditribution $DISTRO_CODE"
sudo tools/osbuild-image-test --arch=$ARCH --distro=$DISTRO_CODE --image-info-path="$(which osbuild-image-info)" --instance-number="${array[0]}" --total-number-of-instances="${array[1]}"
