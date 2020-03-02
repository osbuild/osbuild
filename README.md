OSBuild
=======

Build-Pipelines for Operating System Artifacts

OSBuild is a pipeline-based build system for operating system artifacts. It
defines a universal pipeline description and a build system to execute them,
producing artifacts like operating system images, working towards an image
build pipeline that is more comprehensible, reproducible, and extendable.

See the `osbuild(1)` man-page for details on how to run osbuild, the definition
of the pipeline description, and more.

### Project

 * **Website**: <https://www.osbuild.org>
 * **Bug Tracker**: <https://github.com/osbuild/osbuild/issues>

### Requirements

The requirements for this project are:

 * `python >= 3.7`
 * `systemd-nspawn >= 244`

Additionally, the built-in stages require:

 * `bash >= 5.0`
 * `coreutils >= 8.31`
 * `curl >= 7.68`
 * `qemu-img >= 4.2.0`
 * `rpm >= 4.15`
 * `tar >= 1.32`
 * `util-linux >= 235`

At build-time, the following software is required:

 * `python-docutils >= 0.13`
 * `pkg-config >= 0.29`

### Build

The standard python package system is used. Consult upstream documentation for
detailed help. In most situations the following commands are sufficient to
build and install from source:

```sh
python setup.py build
python setup.py install --skip-build --root=/
```

The man-pages require `python-docutils` and can be built via:

```sh
rst2man docs/<input-file>.rst <output-file>
```

### Repository:

 - **web**:   <https://github.com/osbuild/osbuild>
 - **https**: `https://github.com/osbuild/osbuild.git`
 - **ssh**:   `git@github.com:osbuild/osbuild.git`

### License:

 - **Apache-2.0**
 - See LICENSE file for details.
