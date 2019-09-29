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
        "basearch": "x86_64",
        "repos": {
          "fedora": {
            "metalink": "https://mirrors.fedoraproject.org/metalink?repo=fedora-$releasever&arch=$basearch",
            "gpgkey": "F1D8 EC98 F241 AAF2 0DF6  9420 EF3C 111F CFC6 59B9",
            "checksum": "sha256:9f596e18f585bee30ac41c11fb11a83ed6b11d5b341c1cb56ca4015d7717cb97"
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
    "name": "org.osbuild.qemu",
    "options": {
      "format": "qcow2",
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
usage: python3 -m osbuild [-h] [--build-pipeline PIPELINE] [--store DIRECTORY]
                   [-l DIRECTORY]
                   PIPELINE

Build operating system images

positional arguments:
  PIPELINE              json file containing the pipeline that should be built

optional arguments:
  -h, --help            show this help message and exit
  --build-pipeline PIPELINE
                        json file containing the pipeline to create a build
                        environment
  --store DIRECTORY     the directory where intermediary os trees are stored
  -l DIRECTORY, --libdir DIRECTORY
                        the directory containing stages, assemblers, and the
                        osbuild library
```

### Running example

You can build basic qcow2 image of Fedora 30 by running a following command:

```
sudo python3 -m osbuild --libdir . samples/base-qcow2.json
```

- Root rights are required because osbuild heavily relies on creating
  systemd containers and bind mounting.

  It shouldn't interfere with host OS but please be **careful**! It's still under
  development!

- `--libdir` argument is required because `osbuild` expects itself to be
  installed in directories under `/usr`. Using this argument you can change
  the expected path.

- You don't need to use any kind of virtual environment, modern version of
  Python 3 is enough. `osbuild` uses only standard library and linux commands.

