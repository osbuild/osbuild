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

`osbuild` runs each of stages in turn, somewhat isolating them into mount and
pid namespaces. It injects the `options` object with a `tree` key pointing to
the file system tree and passes that to the stage via its `stdin`.
Stages may have side effects: the `io.weldr.qcow2` stage in the above example
packs the tree into a `qcow2` image.
