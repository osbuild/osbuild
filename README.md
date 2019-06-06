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

`osbuild` runs each of the stages in turn, isolating them into mount and pid
namespaces. It injects the `options` object with a `tree` key pointing to the
file system tree and passes that to the stage via its `stdin`. Each stage has
private `/tmp` and `/var/tmp` directories that are deleted after the stage is
run.

Stages may have side effects: the `io.weldr.qcow2` stage in the above
example packs the tree into a `qcow2` image.

## Running

```
osbuild [--from ARCHIVE] [--save ARCHIVE] PIPELINE
```

Runs `PIPELINE`. If `--from` is given, unpacks its contents (`.tar.gz`) into
the tree before running the first stage. If `--save` is given, saves the
contents of the tree in the given archive.
