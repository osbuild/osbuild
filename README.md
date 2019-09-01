# osbuild

A build system for operating system images, working towards an image build
pipeline that's more comprehensible, reproducible, and extendable.

## Pipelines

The build process for an image is described by a pipeline. Each
[*stage*](/stages) in a pipeline is a program that, given some configuration,
modifies a file system tree. Finally, an assembler takes a filesystem tree, and
assembles it into an image. Pipelines are defined as JSON files like this one:

```json
{
  "name": "Example Image",
  "stages": [
    {
      "name": "org.osbuild.dnf",
      "options": {
        "releasever": "30",
        "repos": {
          "fedora": {
            "name": "Fedora",
            "metalink": "https://mirrors.fedoraproject.org/metalink?repo=fedora-$releasever&arch=$basearch",
            "gpgkey": "file:///etc/pki/rpm-gpg/RPM-GPG-KEY-fedora-$releasever-$basearch"
          }
        },
        "packages": [ "@Core", "grub2-pc", "httpd" ]
        }
    },
    {
      "name": "org.osbuild.systemd",
      "options": {
        "enabled_services": [ "httpd" ]
      }
    },
    {
      "name": "org.osbuild.grub2",
      "options": {
        "root_fs_uuid": "76a22bf4-f153-4541-b6c7-0332c0dfaeac"
      }
    }
  ],
  "assembler": {
    "name": "org.osbuild.qcow2",
    "options": {
      "filename": "example.qcow2",
      "root_fs_uuid": "76a22bf4-f153-4541-b6c7-0332c0dfaeac",
      "size": 3221225472
    }
  }
}
```

`osbuild` runs each of the stages in turn, isolating them from the host and
from each other, with the exception that they all operate on the same
filesystem-tree. The assembler is similarly isolated, and given the same
tree, in read-only mode and assembles it into an image without altering
its contents.

The filesystem tree produced by the final stage of a pipeline, is named
and optionally saved to be reused as the base for future pipelines.

Each stage is passed the (appended) `options` object as JSON over stdin.

The above pipeline has no base and produces a qcow2 image.

## Running

```
usage: python3 -m osbuild [-h] [--store DIRECTORY] [-l DIRECTORY] -o DIRECTORY
                   PIPELINE

Build operating system images

positional arguments:
  PIPELINE              json file containing the pipeline that should be built

optional arguments:
  -h, --help            show this help message and exit
  --store DIRECTORY   the directory where intermediary os trees are stored
  -l DIRECTORY, --libdir DIRECTORY
                        the directory containing stages, assemblers, and the
                        osbuild library

required named arguments:
  -o DIRECTORY, --output DIRECTORY
                        provide the empty DIRECTORY as output argument to the
                        last stage
```
