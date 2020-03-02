=======
osbuild
=======

----------------------------------------------
Build-Pipelines for Operating System Artifacts
----------------------------------------------

:Manual section: 1
:Manual group: User Commands

SYNOPSIS
========

| ``osbuild`` [ OPTIONS ] PIPELINE
| ``osbuild`` [ OPTIONS ] -
| ``osbuild`` ``--help``

DESCRIPTION
===========

**osbuild** is a build-system for operating system artifacts. It takes a
pipeline description as input and produces file-system trees, images, or other
artifacts as output. Its pipeline description gives comprehensive control over
the individual steps to execute as part of a pipeline. **osbuild** provides
isolation from the host system as well as caching capabilities, and thus
ensures that pipeline builds will be deterministic and efficient.

OPTIONS
=======

**osbuild** reads the pipeline description from the file passed on the
command-line. To make **osbuild** read the pipeline description from standard
input, pass ``-``.

The following command-line options are supported. If an option is passed, which
is not listed here, **osbuild** will deny startup and exit with an error.

-h, --help                      print usage information and exit immediately
--build-env=PATH                json file containing a description of the build
                                environment
--store=DIR                     directory where intermediary file system trees
                                are stored
--sources=PATH                  json file containing a dictionary of source
                                configuration
--secrets=PATH                  json file containing a dictionary of secrets
                                that are passed to sources
-l, --libdir=DIR                directory containing stages, assemblers, and
                                the osbuild library
--checkpoint=CHECKPOINT         stage to commit to the object store during
                                build (can be passed multiple times)
--json                          output results in JSON format

PIPELINES
=========

The build process for an image is described by a pipeline. Each *stage* in a
pipeline is a program that, given some configuration, modifies a file system
tree. Finally, an assembler takes a filesystem tree, and assembles it into an
image. Pipelines are defined as JSON files like this one:

|
| {
|   "name": "Example Image",
|   "stages": [
|     {
|       "name": "org.osbuild.dnf",
|       "options": {
|         "releasever": "31",
|         "basearch": "x86_64",
|         "repos": [
|           {
|             "metalink": "https://example.com",
|             "checksum": "sha256:...<checksum>...",
|             "gpgkey": "...<gpg-key>..."
|           }
|         ],
|         "packages": [ "@Core", "grub2-pc", "httpd" ]
|         }
|     },
|     {
|       "name": "org.osbuild.systemd",
|       "options": {
|         "enabled_services": [ "httpd" ]
|       }
|     },
|     {
|       "name": "org.osbuild.grub2",
|       "options": {
|         "root_fs_uuid": "76a22bf4-f153-4541-b6c7-0332c0dfaeac"
|       }
|     }
|   ],
|   "assembler": {
|     "name": "org.osbuild.qemu",
|     "options": {
|       "format": "qcow2",
|       "filename": "example.qcow2",
|       "ptuuid": "0x7e83a7ba",
|       "root_fs_uuid": "76a22bf4-f153-4541-b6c7-0332c0dfaeac",
|       "size": 3221225472
|     }
|   }
| }
|

`osbuild` runs each of the stages in turn, isolating them from the host and
from each other, with the exception that they all operate on the same
filesystem-tree. The assembler is similarly isolated, and given the same
tree, in read-only mode, and assembles it into an image without altering
its contents.

The filesystem tree produced by the final stage of a pipeline, is named
and optionally saved to be reused as the base for future pipelines.

Each stage is passed the (appended) `options` object as JSON over stdin.

The above pipeline has no base and produces a qcow2 image.

EXAMPLES
========

 1. To build a basic qcow2 image of Fedora 30, use:

    ``sudo osbuild --sources samples/sources.json samples/base-qcow2.json``

    Superuser privileges are needed to mount file systems, create loop devices,
    and setup isolation environments.

 2. To run **osbuild** from a local checkout, use:

    ``sudo python3 -m osbuild --libdir . --sources samples/sources.json samples/base-qcow2.json``

    This will make sure to execute the `osbuild` module from the current
    directory, as well as use it to search for stages, assemblers, and more.
