#!/bin/bash
set -euxo pipefail
# Get OS details.
source /etc/os-release
ARCH=$(uname -m)
DISTRO_CODE="${DISTRO_CODE:-${ID}-${VERSION_ID//./}}"

# get manifest-db at the version specified for this arch+distro
MANIFEST_DB_COMMIT=$(cat Schutzfile | jq -r '.global.dependencies."manifest-db".commit')
MANIFEST_DB_REPO="https://github.com/osbuild/manifest-db"
git clone "$MANIFEST_DB_REPO" manifest-db
cd manifest-db
git checkout "$MANIFEST_DB_COMMIT"

# update selinux labels for the image-info tool
OSBUILD_LABEL=$(matchpathcon -n /usr/bin/osbuild)
chcon $OSBUILD_LABEL tools/image-info

# set the maximum cache size to unlimited
echo "{}" | sudo osbuild --cache-max-size unlimited -

# run the tests from the manifest-db for this arch+distro
echo "Running the osbuild-image-test for arch $ARCH and ditribution $DISTRO_CODE"
sudo tools/osbuild-image-test --arch=$ARCH --distro=$DISTRO_CODE --image-info-path=tools/image-info
