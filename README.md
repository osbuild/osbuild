# OSBuild

Build-Pipelines for Operating System Artifacts

OSBuild is a pipeline-based build system for operating system artifacts. It
defines a universal pipeline description and a build system to execute them,
producing artifacts like operating system images, working towards an image
build pipeline that is more comprehensible, reproducible, and extendable.

See the `osbuild(1)` man-page for details on how to run osbuild, the definition
of the pipeline description, and more.

## Project

 * **Website**: https://www.osbuild.org
 * **Bug Tracker**: https://github.com/osbuild/osbuild/issues
 * **Discussions**: https://github.com/orgs/osbuild/discussions
 * **Matrix**: #image-builder on [fedoraproject.org](https://matrix.to/#/#image-builder:fedoraproject.org)
 * **Changelog**: https://github.com/osbuild/osbuild/releases

### Principles

1. [OSBuild stages](./stages) are never broken, only deprecated. The same manifest should always produce the same output.
2. [OSBuild stages](./stages) should be explicit whenever possible instead of e.g. relying on the state of the tree.
3. Pipelines are independent, so the tree is expected to be empty at the beginning of each.
4. Manifests are expected to be machine-generated, so OSBuild has no convenience functions to support manually created manifests.
5. The build environment is confined against accidental misuse, but this should not be considered a security boundary.
6. OSBuild may only use Python language features supported by the oldest target distribution.

### Contributing

Please refer to the [developer guide](https://osbuild.org/docs/developer-guide/index) to learn about our workflow, code style and more.

## Requirements

The requirements for this project are:

 * `bubblewrap >= 0.4.0`
 * `python >= 3.6`

Additionally, the built-in stages require:

 * `bash >= 5.0`
 * `coreutils >= 8.31`
 * `curl >= 7.68`
 * `qemu-img >= 4.2.0`
 * `rpm >= 4.15`
 * `tar >= 1.32`
 * `util-linux >= 235`
 * `skopeo`
 * `python3-librepo`

At build-time, the following software is required:

 * `python-docutils >= 0.13`
 * `pkg-config >= 0.29`

Testing requires additional software:

 * `pytest`

## Build

Osbuild is a python script so it is not compiled.
To verify changes made to the code use included makefile rules:

 * `make lint` to run linter on top of the code
 * `make test-all` to run base set of tests
 * `sudo make test-run` to run extended set of tests (takes long time)

Also keep in mind that some tests require those prerequisites,
otherwise they are skipped

```
sudo dnf install -y systemd-boot-unsigned erofs-utils pykickstart podman xfsprogs
```

## Installation

Installing `osbuild` requires to not only install the `osbuild` module, but also
additional artifacts such as tools (i.e: `osbuild-mpp`) sources, stages, schemas
and SELinux policies.

For this reason, doing an installation from source is not trivial and the easier
way to install it is to create the set of RPMs that contain all these components.

This can be done with the `rpm` make target, i.e:

```sh
make rpm
```

A set of RPMs will be created in the `./rpmbuild/RPMS/noarch/` directory and can
be installed in the system using the distribution package manager, i.e:

```sh
sudo dnf install ./rpmbuild/RPMS/noarch/*.rpm
```

## Repository

 - **web**:   https://github.com/osbuild/osbuild
 - **https**: `https://github.com/osbuild/osbuild.git`
 - **ssh**:   `git@github.com:osbuild/osbuild.git`

## License

 - **Apache-2.0**

   See LICENSE file for details.

 - osbuild/util/_writer.py: Taken from [tomli-w](https://github.com/hukkin/tomli-w).

   MIT License

   Copyright (c) 2021 Taneli Hukkinen

   Permission is hereby granted, free of charge, to any person obtaining a copy
   of this software and associated documentation files (the "Software"), to deal
   in the Software without restriction, including without limitation the rights
   to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
   copies of the Software, and to permit persons to whom the Software is
   furnished to do so, subject to the following conditions:

   The above copyright notice and this permission notice shall be included in all
   copies or substantial portions of the Software.

   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
   FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
   AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
   LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
   OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
   SOFTWARE.
