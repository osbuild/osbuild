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
        "repos": [
          {
            "metalink": "https://mirrors.fedoraproject.org/metalink?repo=fedora-$releasever&arch=$basearch",
            "checksum": "sha256:9f596e18f585bee30ac41c11fb11a83ed6b11d5b341c1cb56ca4015d7717cb97",
            "gpgkey": "-----BEGIN PGP PUBLIC KEY BLOCK-----\n\nmQINBFturGcBEACv0xBo91V2n0uEC2vh69ywCiSyvUgN/AQH8EZpCVtM7NyjKgKm\nbbY4G3R0M3ir1xXmvUDvK0493/qOiFrjkplvzXFTGpPTi0ypqGgxc5d0ohRA1M75\nL+0AIlXoOgHQ358/c4uO8X0JAA1NYxCkAW1KSJgFJ3RjukrfqSHWthS1d4o8fhHy\nKJKEnirE5hHqB50dafXrBfgZdaOs3C6ppRIePFe2o4vUEapMTCHFw0woQR8Ah4/R\nn7Z9G9Ln+0Cinmy0nbIDiZJ+pgLAXCOWBfDUzcOjDGKvcpoZharA07c0q1/5ojzO\n4F0Fh4g/BUmtrASwHfcIbjHyCSr1j/3Iz883iy07gJY5Yhiuaqmp0o0f9fgHkG53\n2xCU1owmACqaIBNQMukvXRDtB2GJMuKa/asTZDP6R5re+iXs7+s9ohcRRAKGyAyc\nYKIQKcaA+6M8T7/G+TPHZX6HJWqJJiYB+EC2ERblpvq9TPlLguEWcmvjbVc31nyq\nSDoO3ncFWKFmVsbQPTbP+pKUmlLfJwtb5XqxNR5GEXSwVv4I7IqBmJz1MmRafnBZ\ng0FJUtH668GnldO20XbnSVBr820F5SISMXVwCXDXEvGwwiB8Lt8PvqzXnGIFDAu3\nDlQI5sxSqpPVWSyw08ppKT2Tpmy8adiBotLfaCFl2VTHwOae48X2dMPBvQARAQAB\ntDFGZWRvcmEgKDMwKSA8ZmVkb3JhLTMwLXByaW1hcnlAZmVkb3JhcHJvamVjdC5v\ncmc+iQI4BBMBAgAiBQJbbqxnAhsPBgsJCAcDAgYVCAIJCgsEFgIDAQIeAQIXgAAK\nCRDvPBEfz8ZZudTnD/9170LL3nyTVUCFmBjT9wZ4gYnpwtKVPa/pKnxbbS+Bmmac\ng9TrT9pZbqOHrNJLiZ3Zx1Hp+8uxr3Lo6kbYwImLhkOEDrf4aP17HfQ6VYFbQZI8\nf79OFxWJ7si9+3gfzeh9UYFEqOQfzIjLWFyfnas0OnV/P+RMQ1Zr+vPRqO7AR2va\nN9wg+Xl7157dhXPCGYnGMNSoxCbpRs0JNlzvJMuAea5nTTznRaJZtK/xKsqLn51D\nK07k9MHVFXakOH8QtMCUglbwfTfIpO5YRq5imxlWbqsYWVQy1WGJFyW6hWC0+RcJ\nOx5zGtOfi4/dN+xJ+ibnbyvy/il7Qm+vyFhCYqIPyS5m2UVJUuao3eApE38k78/o\n8aQOTnFQZ+U1Sw+6woFTxjqRQBXlQm2+7Bt3bqGATg4sXXWPbmwdL87Ic+mxn/ml\nSMfQux/5k6iAu1kQhwkO2YJn9eII6HIPkW+2m5N1JsUyJQe4cbtZE5Yh3TRA0dm7\n+zoBRfCXkOW4krchbgww/ptVmzMMP7GINJdROrJnsGl5FVeid9qHzV7aZycWSma7\nCxBYB1J8HCbty5NjtD6XMYRrMLxXugvX6Q4NPPH+2NKjzX4SIDejS6JjgrP3KA3O\npMuo7ZHMfveBngv8yP+ZD/1sS6l+dfExvdaJdOdgFCnp4p3gPbw5+Lv70HrMjA==\n=BfZ/\n-----END PGP PUBLIC KEY BLOCK-----\n"
          }
        ],
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
      "ptuuid": "0x7e83a7ba",
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
usage: __main__.py [-h] [--build-env ENV] [--store DIRECTORY] [-l DIRECTORY]
                   [--json]
                   PIPELINE

Build operating system images

positional arguments:
  PIPELINE              json file containing the pipeline that should be
                        built, or a '-' to read from stdin

optional arguments:
  -h, --help            show this help message and exit
  --build-env ENV       json file containing a description of the build
                        environment
  --store DIRECTORY     the directory where intermediary os trees are stored
  -l DIRECTORY, --libdir DIRECTORY
                        the directory containing stages, assemblers, and the
                        osbuild library
  --json                output results in JSON format
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

