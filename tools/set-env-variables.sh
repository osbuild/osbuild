#!/bin/bash
# don't error on unused ARCH and DISTRO_CODE variables
# shellcheck disable=SC2034

source /etc/os-release
ARCH=$(uname -m)
DISTRO_CODE="${DISTRO_CODE:-${ID}-${VERSION_ID//./}}"
