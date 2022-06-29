#!/usr/bin/python3
"""
Encode binary file data within the manifest by using
the org.osbuild.inline source.
"""

import argparse
import binascii
import hashlib
import json
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("FILE", help="The file to encode")
    args = parser.parse_args()

    with open(args.FILE, "rb") as f:
        raw = f.read()

    m = hashlib.sha256()
    m.update(raw)
    checksum = "sha256:" + m.hexdigest()
    data = binascii.b2a_base64(raw, newline=False).decode("ascii")

    source = {"org.osbuild.inline": {"items": {checksum: {"encoding": "base64", "data": data}}}}

    json.dump(source, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
