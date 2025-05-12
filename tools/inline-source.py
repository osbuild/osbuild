#!/usr/bin/python3
"""
Encode binary file data within the manifest by using
the org.osbuild.inline source.
"""

import argparse
import base64
import hashlib
import json
import lzma
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("FILE", help="The file to encode")
    parser.add_argument(
        "-e",
        "--encoding",
        choices=["base64", "lzma+base64"],
        default="base64",
        help="The encoding to use for the data (default: base64)"
    )
    args = parser.parse_args()

    with open(args.FILE, "rb") as f:
        raw = f.read()

    m = hashlib.sha256()
    m.update(raw)
    checksum = "sha256:" + m.hexdigest()

    if args.encoding == "lzma+base64":
        raw = lzma.compress(raw)
        data = base64.b64encode(raw).decode("ascii")
    else:
        # default to base64
        data = base64.b64encode(raw).decode("ascii")

    source = {
        "org.osbuild.inline": {
            "items": {
                checksum: {
                    "encoding": args.encoding,
                    "data": data
                }
            }
        }
    }

    json.dump(source, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
