#!/bin/bash
set -euxo pipefail

# Get OS details.
source /etc/os-release

WORKING_DIRECTORY=/usr/libexec/osbuild-composer
IMAGE_TEST_CASE_RUNNER=/usr/libexec/tests/osbuild-composer/osbuild-image-tests
IMAGE_TEST_CASES_PATH=/usr/share/tests/osbuild-composer/cases

pushd $WORKING_DIRECTORY
  ${IMAGE_TEST_CASE_RUNNER} -test.v \
    $(ls ${IMAGE_TEST_CASES_PATH}/${ID}_${VERSION_ID%.*}-$(uname -m)-*-boot.json)
popd