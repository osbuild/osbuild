#!/bin/bash
set -euxo pipefail

# Clone osbuild-composer.
git clone --depth 1 https://github.com/osbuild/osbuild-composer

# Move the repository file into place so the osbuild-composer CI scripts can
# copy it into place.
mv ${WORKSPACE}/osbuild-mock.repo osbuild-composer/

# Change the workspace directory to point to where osbuild-composer is cloned.
WORKSPACE=${WORKSPACE}/osbuild-composer
export WORKSPACE

# Deploy osbuild-composer/osbuild and run the image tests.
pushd osbuild-composer
    schutzbot/deploy.sh
    schutzbot/run_image_tests.sh
popd