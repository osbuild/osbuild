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
echo "{}" | sudo osbuild --store /var/lib/osbuild/store --cache-max-size unlimited -

IFS='/' read -r -a array <<< $1

# poor mans cache action
curl "https://awscli.amazonaws.com/awscli-exe-linux-${ARCH}.zip" -o "awscliv2.zip"
unzip -q awscliv2.zip
sudo ./aws/install

mkdir -p /var/lib/osbuild/store
S3_PATH="osbuild-ci-cache/${ARCH}-${DISTRO_CODE}/"
AWS_ACCESS_KEY_ID="$V2_AWS_ACCESS_KEY_ID" \
 AWS_SECRET_ACCESS_KEY="$V2_AWS_SECRET_ACCESS_KEY" \
  aws s3 sync "s3://${S3_PATH}/" /var/lib/osbuild/store --quiet || true
# debug
ls -a /var/lib/osbuild/store

# run the tests from the manifest-db for this arch+distro
echo "Running the osbuild-image-test for arch $ARCH and ditribution $DISTRO_CODE"
sudo tools/osbuild-image-test --arch=$ARCH --distro=$DISTRO_CODE --image-info-path=tools/image-info --instance-number="${array[0]}" --total-number-of-instances="${array[1]}"

# store the store
# TOOD: trim at some point as this will grow boundlessly
aws s3 sync /var/lib/osbuild/store "s3://${S3_PATH}" --quiet
