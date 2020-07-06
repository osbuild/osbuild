#!/bin/bash
set -euo pipefail

# Get OS details.
source /etc/os-release

WORKING_DIRECTORY=/usr/libexec/osbuild-composer
IMAGE_TEST_CASE_RUNNER=/usr/libexec/tests/osbuild-composer/osbuild-image-tests
IMAGE_TEST_CASES_PATH=/usr/share/tests/osbuild-composer/cases

PASSED_TESTS=()
FAILED_TESTS=()

TEST_CASES=(
  "openstack-boot.json"
  "qcow2-boot.json"
  "tar-boot.json"
  "vhd-boot.json"
  "vmdk-boot.json"
)

# Print out a nice test divider so we know when tests stop and start.
test_divider () {
    printf "%0.s-" {1..78} && echo
}

# Get the full test case name based on distro and architecture.
get_full_test_case () {
    echo "${IMAGE_TEST_CASES_PATH}/${ID}_${VERSION_ID%.*}-$(uname -m)-${1}"
}

# Run a test case and store the result as passed or failed.
run_test_case () {
    TEST_RUNNER=$1
    TEST_CASE_FILENAME=$2
    TEST_NAME=$(basename $TEST_CASE_FILENAME)

    echo
    test_divider
    echo "🏃🏻 Running test: ${TEST_NAME}"
    test_divider

    if sudo $TEST_RUNNER -test.v $TEST_CASE_FILENAME 2>&1 | tee ${WORKSPACE}/${TEST_NAME}.log; then
        PASSED_TESTS+=("$TEST_NAME")
    else
        FAILED_TESTS+=("$TEST_NAME")
    fi

    test_divider
    echo
}

# Ensure osbuild-composer-tests is installed.
sudo dnf -y install osbuild-composer-tests

# Change to the working directory.
cd $WORKING_DIRECTORY

# Run each test case.
for TEST_CASE in "${TEST_CASES[@]}"; do
    TEST_CASE_FILENAME=$(get_full_test_case $TEST_CASE)
    run_test_case $IMAGE_TEST_CASE_RUNNER $TEST_CASE_FILENAME
done

# Print a report of the test results.
test_divider
echo "😃 Passed tests: " "${PASSED_TESTS[@]}"
echo "☹ Failed tests: " "${FAILED_TESTS[@]}"
test_divider

# Exit with a failure if any tests failed.
if [ ${#FAILED_TESTS[@]} -eq 0 ]; then
    echo "🎉 All tests passed."
    exit 0
else
    echo "🔥 One or more tests failed."
    exit 1
fi