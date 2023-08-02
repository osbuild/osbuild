#!/usr/bin/python3
"""Collect to be installed packages of a lorax template script

This simple tool intercepts all `installpkg` commands of a lorax
template script like `runtime-install.tmpl` in order to collect
all to be installed packages. The result is presented on stdout
in form of a JSON array.
"""

import argparse
import fnmatch
import json
import os
import sys
import tempfile

import dnf
import dnf.conf
import dnf.conf.read

import osbuild.util.osrelease as ostrelease
from osbuild.util.lorax import render_template


class DepSolver:
    def __init__(self, arch, relver, dirs):
        self.base = dnf.Base()
        self.arch = arch
        self.basearch = dnf.rpm.basearch(arch)
        conf = self.base.conf
        conf.config_file_path = "/dev/null"
        conf.persistdir = dirs["persistdir"]
        conf.cachedir = dirs["cachedir"]
        conf.substitutions["arch"] = arch
        conf.substitutions["basearch"] = self.basearch
        conf.substitutions["releasever"] = relver
        conf.reposdir = [dirs["repodir"]]
        self.repos = self.read_repos()

    def read_repos(self):
        conf = self.base.conf
        reader = dnf.conf.read.RepoReader(conf, {})
        return {r.id: r for r in reader}

    def reset(self):
        base = self.base
        base.reset(goal=True, repos=True, sack=True)

        for repo in self.repos.values():
            base.repos.add(repo)

        base.fill_sack(load_system_repo=False)

    def filter(self, pkg):
        sack = self.base.sack
        return dnf.subject.Subject(pkg).get_best_query(sack).filter(latest=True)

    def install(self, packages, excludes=None, optional=False):
        def included(pkg):
            for exclude in excludes or []:
                if fnmatch.fnmatch(pkg.name, exclude):
                    return False
            return True

        result = []

        for p in packages:
            pkgs = self.filter(p)
            if not pkgs:
                if optional:
                    continue
                raise dnf.exceptions.PackageNotFoundError("no package matched", p)

            result.extend(map(lambda p: p.name, filter(included, pkgs)))

        return result


def list_packages(text, solver):
    parser = argparse.ArgumentParser()
    parser.add_argument("--optional", action="store_true", default=False)
    parser.add_argument("--except", dest="excludes", action="append")
    parser.add_argument("packages", help="The template to process", nargs="*")

    packages = []
    for line in text:
        cmd, args = line[0], parser.parse_args(line[1:])

        if cmd != "installpkg":
            print(f"{cmd} ignored", file=sys.stderr)
            continue

        pkgs = solver.install(args.packages, None, args.optional)
        packages += pkgs

    return packages


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--basearch", help="Set the `basearch` variable", default="x86_64")
    parser.add_argument("--product", help="Set the `product` variable", default="fedora")
    parser.add_argument(
        "--dnf-cache", metavar="PATH", type=os.path.abspath, default=None, help="Path to DNF cache-directory to use"
    )
    parser.add_argument(
        "--repo-dir",
        metavar="PATH",
        type=os.path.abspath,
        default="/etc/yum.repos.d",
        help="Path to DNF repositories directory",
    )
    parser.add_argument("--os-version", metavar="PATH", default=None, help="OS version to use for dnf")
    parser.add_argument("FILE", help="The template to process")
    args = parser.parse_args()

    variables = {"basearch": args.basearch, "product": args.product}

    txt = render_template(args.FILE, variables)

    packages = []

    os_version = args.os_version
    if not os_version:
        release = ostrelease.parse_files(*ostrelease.DEFAULT_PATHS)
        os_version = release["VERSION_ID"]

    with tempfile.TemporaryDirectory(dir="/var/tmp") as tmp:
        persistdir = os.path.join(tmp, "dnf-persist")
        cachedir = args.dnf_cache or os.path.join(tmp, "dnf-cache")
        dirs = {"persistdir": persistdir, "cachedir": cachedir, "repodir": args.repo_dir}

        solver = DepSolver(args.basearch, os_version, dirs)
        solver.reset()

        packages = list_packages(txt, solver)

    json.dump(packages, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
