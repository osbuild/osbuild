#!/usr/bin/bash
#
# Create a container as an oci-archive that contains /dev/null.
#
# Used to test embedding containers that contain device nodes in ostree commits
# (https://github.com/coreos/rpm-ostree/pull/5114).
#
# Requires root to create the node and to copy it into the container image.

set -euxo pipefail

tmpdir=$(mktemp -d -p .)

cleanup() {
    rm -r "${tmpdir}"
}
trap cleanup EXIT

echo "This is a simple container that contains /dev/null for testing rpm-ostree commit creation." > "${tmpdir}/README"

mkdir "${tmpdir}/dev"
mknod -m 666 "${tmpdir}/dev/null" c 1 3

amd=$(buildah from --arch=amd64 scratch)
buildah config --created-by "Achilleas Koutsou" "${amd}"
buildah copy "${amd}" "${tmpdir}" /
buildah commit --format=oci --rm "${amd}" oci-archive:container-with-devnull.tar
