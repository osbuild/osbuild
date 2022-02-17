#!/bin/bash
set -euo pipefail

# Get OS and architecture details.
source /usr/libexec/osbuild-test/set-env-variables.sh

if [[ -n "$CI_BUILD_ID" ]]; then
    BUILD_ID="${BUILD_ID:-${CI_BUILD_ID}}"
else
    BUILD_ID="${BUILD_ID:-$(uuidgen)}"
fi

WORKING_DIRECTORY=/usr/libexec/osbuild-composer
IMAGE_TEST_CASE_RUNNER=/usr/libexec/osbuild-test/osbuild-image-tests
IMAGE_TEST_CASES_PATH=/usr/share/tests/osbuild/image-info

# aarch64 machines in AWS don't supported nested KVM so we run only
# testing against cloud vendors, don't boot with qemu-kvm!
if [[ "${ARCH}" == "aarch64" ]]; then
    IMAGE_TEST_CASE_RUNNER="${IMAGE_TEST_CASE_RUNNER} --disable-local-boot"
fi

# Skip 'selinux/contect-mismatch' part of the image-info report on RHEL-8.
# https://bugzilla.redhat.com/show_bug.cgi?id=1973754
if [[ "${DISTRO_CODE}" =~ "rhel-84" ]]; then
    IMAGE_TEST_CASE_RUNNER="${IMAGE_TEST_CASE_RUNNER} -skip-selinux-ctx-check"
fi

# Skip the /usr/lib/tmpfiles.d/rpm-ostree-1-autovar.conf file form the 'tmpfiles.d'
# section of the image-info report. The content of the file is dynamically generated
# and lines are not deterministically sorted, thus the diff often fails.
if [[ "${DISTRO_CODE}" =~ "fedora" ]]; then
    IMAGE_TEST_CASE_RUNNER="${IMAGE_TEST_CASE_RUNNER} -skip-tmpfilesd-path /usr/lib/tmpfiles.d/rpm-ostree-1-autovar.conf"
fi

PASSED_TESTS=()
FAILED_TESTS=()

# Print out a nice test divider so we know when tests stop and start.
test_divider () {
    printf "%0.s-" {1..78} && echo
}

# Get a list of test cases.
get_test_cases () {
    TEST_CASE_SELECTOR="${DISTRO_CODE/-/_}-${ARCH}"
    pushd $IMAGE_TEST_CASES_PATH > /dev/null
        ls "$TEST_CASE_SELECTOR"*.json
    popd > /dev/null
}

# Run a test case and store the result as passed or failed.
run_test_case () {
    TEST_RUNNER=$1
    TEST_CASE_FILENAME=$2
    TEST_NAME=$(basename "$TEST_CASE_FILENAME")

    echo
    test_divider
    echo "🏃🏻 Running test: ${TEST_NAME}"
    test_divider

    TEST_CMD="env BRANCH_NAME=${BRANCH_NAME-main} BUILD_ID=$BUILD_ID DISTRO_CODE=$DISTRO_CODE $TEST_RUNNER -test.v ${IMAGE_TEST_CASES_PATH}/${TEST_CASE_FILENAME}"

    # Run the test and add the test name to the list of passed or failed
    # tests depending on the result.
    # shellcheck disable=SC2086 # We need to pass multiple arguments here.
    if sudo -E $TEST_CMD 2>&1 | tee "${WORKSPACE}"/"${TEST_NAME}".log; then
        PASSED_TESTS+=("$TEST_NAME")
    else
        FAILED_TESTS+=("$TEST_NAME")
    fi

    test_divider
    echo
}

# Provision the software under test.
# TODO :remove?
# /usr/libexec/osbuild-composer-test/provision.sh

# Change to the working directory.
cd $WORKING_DIRECTORY

# Workaround the problem that 'image-info' can not read SELinux labels unknown to the host from the image
OSBUILD_LABEL=$(matchpathcon -n "$(which osbuild)")
sudo chcon "$OSBUILD_LABEL" /usr/libexec/osbuild-test/image-info

# Run each test case.
for TEST_CASE in $(get_test_cases); do
    run_test_case "$IMAGE_TEST_CASE_RUNNER" "$TEST_CASE"
done

# Print a report of the test results.
test_divider
echo "😃 Passed tests: " "${PASSED_TESTS[@]}"
echo "☹ Failed tests: " "${FAILED_TESTS[@]}"
test_divider

# Exit with a failure if tests were executed and any of them failed.
if [ ${#PASSED_TESTS[@]} -gt 0 ] && [ ${#FAILED_TESTS[@]} -eq 0 ]; then
    echo "🎉 All tests passed."
    exit 0
else
    echo "🔥 One or more tests failed."
    exit 1
fi
