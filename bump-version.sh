#!/bin/bash

current_version=$(python3 setup.py --version)
new_version=$(expr "${current_version}" + 1)

sed -i "s|Version:\s*${current_version}|Version:\\t${new_version}|" osbuild.spec
sed -i "s|Release:\s*[[:digit:]]\+|Release:\\t1|" osbuild.spec
sed -i "s|version=\"${current_version}\"|version=\"${new_version}\"|" setup.py
