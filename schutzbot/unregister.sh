#!/bin/bash

# Colorful output.
function greenprint {
    echo -e "\033[1;32m[$(date -Isecond)] ${1}\033[0m"
}
function redprint {
    echo -e "\033[1;31m[$(date -Isecond)] ${1}\033[0m"
}

if ! hash subscription-manager; then
    exit 0
fi
if ! sudo subscription-manager status; then
    exit 0
fi
if sudo subscription-manager unregister; then
    greenprint "Host unregistered."
    exit 0
fi
redprint "Failed to unregister"
exit 1
