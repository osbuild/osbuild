#!/bin/bash
set -euxo pipefail

# Install packages.
sudo dnf -y install ansible perl-XML-XPath

get_fastest_mirror() {
  FEDORA_VERSION=${1:-31}
  curl -s "https://mirrors.fedoraproject.org/metalink?repo=fedora-${FEDORA_VERSION}&arch=x86_64" | \
    xpath -e "/metalink/files/file/resources/url[@protocol='http']/text()" 2>/dev/null | \
    head -n 1 | \
    sed 's#releases.*##' || true
}

# Clone the latest version of ansible-osbuild.
git clone https://github.com/osbuild/ansible-osbuild.git ansible-osbuild

# Get the current SHA of osbuild.
OSBUILD_VERSION=$(git rev-parse HEAD)

# Run the deployment.
pushd ansible-osbuild
  echo -e "[test_instances]\nlocalhost ansible_connection=local" > hosts.ini
  ansible-playbook \
    -i hosts.ini \
    -e osbuild_repo=${WORKSPACE} \
    -e osbuild_version=${OSBUILD_VERSION} \
    playbook.yml
popd

# Modify the URLs in the test cases to use a nearby mirror.
TEST_CASE_DIR=/usr/share/tests/osbuild-composer
FASTEST_MIRROR=$(get_fastest_mirror)
sed -i "s#http://download.fedoraproject.org/pub/fedora/linux/releases/#${FASTEST_MIRROR}releases/#" test/pipelines/*.json

# Run a boot test
python3 -m unittest -v test.test_boot