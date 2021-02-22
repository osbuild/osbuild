#!/usr/bin/python3
"""Collect to be installed packages of a lorax template script

This simple tool intercepts all `installpkg` commands of a lorax
template script like `runtime-install.tmpl` in order to collect
all to be installed packages. The result is presented on stdout
in form of a JSON array.
"""

import argparse
import json
import sys

from osbuild.util.lorax import render_template


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--basearch", help="Set the `basearch` variable", default="x86_64")
    parser.add_argument("--product", help="Set the `product` variable", default="fedora")
    parser.add_argument("FILE", help="The template to process")
    args = parser.parse_args()

    variables = {
      "basearch": args.basearch,
      "product": args.product
    }

    txt = render_template(args.FILE, variables)

    packages = []
    optional = []
    excludes = []

    parser =  argparse.ArgumentParser()
    parser.add_argument("--optional", action="append")
    parser.add_argument("--except", dest="excludes", action="append")
    parser.add_argument("packages", help="The template to process", nargs="*")

    for line in txt:
        cmd, args = line[0], parser.parse_args(line[1:])

        if cmd != "installpkg":
            print(f"{cmd} ignored", file=sys.stderr)
            continue

        if args.optional:
            optional += args.optional
        if args.excludes:
            excludes += args.excludes
        if args.packages:
            packages += args.packages

    data = {
        "packages": packages,
        "optional": optional,
        "except": excludes
    }

    json.dump(data, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
