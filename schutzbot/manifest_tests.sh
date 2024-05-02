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
git checkout "$MANIFEST_DB_COMMIT"

# update selinux labels for the image-info tool
OSBUILD_LABEL=$(matchpathcon -n /usr/bin/osbuild)
chcon $OSBUILD_LABEL tools/image-info

# set the maximum cache size to unlimited
echo "{}" | sudo osbuild --store /var/lib/osbuild/store --cache-max-size unlimited -

IFS='/' read -r -a array <<< $1

# run the tests from the manifest-db for this arch+distro
echo "Running the osbuild-image-test for arch $ARCH and ditribution $DISTRO_CODE"

# tweak for more debug visiblity (should go upstream)
sudo dnf install -y patch
cat <<EOF | patch -p1
diff --git a/tools/osbuild-image-test b/tools/osbuild-image-test
index aee8269..f4ed100 100755
--- a/tools/osbuild-image-test
+++ b/tools/osbuild-image-test
@@ -60,6 +60,8 @@ class OSBuild:
             "--store", os.fspath(self.store),
             "--output-dir", os.fspath(self.outdir),
             "--json",
+            # improve visibility for real errors by logging to stderr
+            "--monitor=LogMonitor", "--monitor-fd=2",
         ]
 
         if args:
EOF
sudo tools/osbuild-image-test --arch=$ARCH --distro=$DISTRO_CODE --image-info-path=tools/image-info --instance-number="${array[0]}" --total-number-of-instances="${array[1]}"
