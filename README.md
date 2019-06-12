# osbuild

A build system for operating system images, working towards an image build
pipeline that's more comprehensible, reproducible, and extendable.

## Pipelines

The build process for an image is described by a pipeline. Each
[*stage*](/stages) in a pipeline is a program that, given some configuration,
modifies a file system tree. Pipelines are defined as JSON files like this one:

```json
{
  "name": "Example Image",
  "pipeline": [
    {
      "name": "io.weldr.dnf",
      "options": {
        "packages": [ "@core", "httpd" ]
      }
    },
    {
      "name": "io.weldr.systemd",
      "options": {
        "enabled_services": [ "httpd" ]
      }
    },
    {
      "name": "io.weldr.qcow2",
      "options": {
        "target": "output.qcow2"
      }
    }
  ]
}
```

`osbuild` runs each of the stages in turn, isolating them from the host and
from each other, with the exception that the first stage may be given an input
directory, the last stage an output directory and all stages of a given
pipeline are given the same filesystem tree to operate on.

Each stage is passed the (appended) `options` object as JSON over stdin.

The above pipeline has no input and produces a qcow2 image.

## Running

```
osbuild [--input DIRECTORY] [--output DIRECTORY] PIPELINE
```

Runs `PIPELINE`. If `--input` is given, the directory is available
read-only in the first stage. If `--output` is given it, it must be empty
and is avialble read-write in the final stage.
