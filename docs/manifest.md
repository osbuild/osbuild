# Purpose

This document is a guide to help understand the osbuild manifest. It follows the format of a tutorial, starting from the simplest instance of a valid manifest and builds up to a full example, step by step. This guide aims to be an in-depth explanation of how osbuild processes manifests to build filesystem trees and operating system artifacts. It is not, however, a full guide for the inner workings and design of osbuild itself. Therefore, while this guide is useful for contributors to osbuild, it is not sufficient for understanding the project as a whole.

In addition to osbuild contributors, this guide is useful for:
- Developers of and contributors to manifest generator tools:
    - [osbuild/images](https://github.com/osbuild/images) (the osbuild image definition library) and the projects that use it:
        - [osbuild-composer](https://github.com/osbuild/osbuild-composer).
        - [image-builder-cli](https://github.com/osbuild/image-builder-cli).
        - [bootc-image-builder](https://github.com/osbuild/bootc-image-builder).
    - [osbuild-mpp](https://github.com/osbuild/blob/main/tools/osbuild-mpp)
- Authors of osbuild modules ([stages](https://github.com/osbuild/osbuild/tree/main/stages), [sources](https://github.com/osbuild/osbuild/tree/main/sources), [inputs](https://github.com/osbuild/osbuild/tree/main/inputs), [mounts](https://github.com/osbuild/osbuild/tree/main/mounts), [devices](https://github.com/osbuild/osbuild/tree/main/devices)).

# Introduction

At its core, osbuild is a pipeline processor. It reads instructions from a json file (manifest) and executes them in order, transforming a filesystem tree (directory) at each step of the process. Each pipeline consists of a series of instructions (stages). It starts with an empty filesystem tree and each stage modifies it in a specific way. Typically, but not always, these modifications work towards creating an operating system image. However, there is nothing inherent to the design or structure of a manifest that explicitly enables building operating system artifacts. It is through the choice of stages and certain parts of osbuild's internals that this particular use case is achieved. A lot of the examples we will use in this guide will not be producing operating system artifacts (images, root trees, etc), but will be very simple pipelines meant to demonstrate how osbuild operates. After the basics have been covered and understood, it will be easier to understand how a more realistic manifest can be made to create an operating system image.

# The manifest

[Principle 4](https://osbuild.org/docs/developer-guide/projects/osbuild/#principles) of osbuild states that "Manifests are expected to be machine-generated, so OSBuild has no convenience functions to support manually created manifests". That said, it's still entirely possible to write simple manifests by hand, they just wont be very interesting. Before we look at a complete manifest, let's first describe the general structure:
```json
{
  "version": "2",
  "pipelines": [
    {
      "name": "tree",
      "stages": []
    }
  ],
  "sources": []
}
```
The `version` isn't very interesting. As of this writing, all manifests are version 2. Version 1 manifests, while still valid, are considered deprecated and there is no (current) plan for a new version on the horizon.
Pipelines are defined under `pipelines`, which is an array of objects, each with a name and a series of stages. This pipeline isn't complete, but for the purposes of this section, these are the important properties.
The last top-level property is something we haven't mentioned so far: `sources`. Sources define resources that will need to be retrieved and provided to stages. Sources are processed before pipeline processing begins and are the only way to provide external artifacts (files, containers, etc) to stages.

## Pipelines

As mentioned above, a pipeline is defined as a series of stages that operate on a filesystem tree. At the start of a pipeline, the tree is completely new and empty. Each stage modifies the tree in a specific way, transforming it step by step towards a desired end state. We haven't described stages in depth yet but, for now, it's enough to think of them as single-purpose executables. With that in mind, consider a pipeline with the following series of stages:
1. org.osbuild.rpm
2. org.osbuild.locale
3. org.osbuild.timezone

The first stage, `org.osbuild.rpm`, will install a set of rpms into the new, empty tree (we'll see where those rpms come from and how they're defined later). `org.osbuild.locale` will set the system locale and `org.osbuild.timezone` sets the system timezone.
If we assume the rpms installed in the first stage are the ones included in the `@core` Fedora package group, it's not hard to imagine what the resulting filesystem tree will look like. It will be the full tree of an operating system, composed of all the files that come from the `@core` packages, and two extra or modified files, `etc/localtime` and `etc/locale.conf` set to the desired values.
This is actually a simplified version of the pipeline that's used in practice to create the operating system tree for most conventional images.

## Stages

Stages, as we already mentioned, are little single-purpose executables, each identified by a unique name (`type`). Stages are defined in the `stages/` directory of the osbuild source tree and are installed in the `stages/` directory of the osbuild libdir (typically, `/usr/lib/osbuild/`). Most stage types are named after the tool they invoke, so if the name of a stage looks like a command or program you're familiar with, that's probably what it's calling. For example, `org.osbuild.tar`, `org.osbuild.truncate`, and `org.osbuild.rpm` run `tar`, `truncate`, and `rpm` respectively. The `org.osbuild.` prefix serves as a namespace for the official upstream stages. This allows external stages to be included and used while avoiding name collisions.
Most stage types define a set of options that they support. Stage options usually map to command line options and flags, though they usually only implement the ones necessary for image building. More stage options are added as the need arises.
The options that a stage supports are defined in an accompanying jsonschema, stored alongside a stage with the `.meta.json` suffix. Looking at the `org.osbuild.truncate` stage as a simple example, the schema is currently defined as follows:
```json
{
  "additionalProperties": false,
  "required": [
    "filename",
    "size"
  ],
  "properties": {
    "filename": {
      "description": "Image filename",
      "type": "string"
    },
    "size": {
      "description": "New desired size",
      "type": "string"
    }
  }
}
```
so the stage in a manifest would look like:
```json
{
  "type": "org.osbuild.truncate",
  "options": {
    "filename": "/newfile",
    "size": "1G"
  }
}
```
When this stage runs, it will create a 1 GiB file named `newfile` in the root of the pipeline's tree.
Another simple stage is `org.osbuild.chmod`, which calls `chmod` to change the mode bits of a file or directory. This is the current schema for the stage:
```json
{
  "options": {
    "additionalProperties": false,
    "properties": {
      "items": {
        "type": "object",
        "additionalProperties": false,
        "patternProperties": {
          "^\\/(?!\\.\\.)((?!\\/\\.\\.\\/).)+$": {
            "type": "object",
            "required": [
              "mode"
            ],
            "properties": {
              "mode": {
                "type": "string",
                "description": "Symbolic or numeric octal mode"
              },
              "recursive": {
                "type": "boolean",
                "description": "Change modes recursively",
                "default": false
              }
            }
          }
        }
      }
    }
  }
}
```
If we write the stage in a manifest as follows:
```json
{
  "type": "org.osbuild.chmod",
    "options": {
      "items": {
        "/newfile": {
          "mode": "0444"
        }
      }
    }
}
```
then running the stage will change the mode of `newfile` to `0444` (`-r--r--r--`).

## Aside: Other modules

Stages are considered "modules" in osbuild. They are drop-in executables that provide simple functionality when run. Other types of modules also exist:
- Sources: Mentioned already above, sources are modules that are defined at the top level of the manifest and are meant to provide the build environment with resources.
- Inputs: In order for a source object (a file, directory, archive, etc) to be accessible to a stage, it needs to be defined in the stage's inputs. While a source defines how to retrieve a file an input makes that file accessible to a stage when it's running. Inputs are also used to retrieve files from another pipeline.
- Devices: A device is used to create or manage device nodes (`/dev/...`) for stages. The most common use case for a device is to set up loop devices for disk images to be partitioned and mounted.
- Mounts: Creates and manages mounts from devices so the tree of a mounted filesystem can be manipulated by a stage.

We'll learn more about these other types of modules later.

## Let's write a manifest

Let's put some stages together and write a simple but complete and valid manifest.
```json
{
  "version": "2",
  "pipelines": [
    {
      "name": "tree",
      "stages": [
        {
          "type": "org.osbuild.truncate",
          "options": {
            "filename": "/newfile",
            "size": "1G"
          }
        },
        {
          "type": "org.osbuild.chmod",
          "options": {
            "items": {
              "/newfile": {
                "mode": "0444"
              }
            }
          }
        }
      ]
    }
  ]
}
```

Save this to a file called `example-1.json` and validate it using osbuild with the following command:
```
$ osbuild example-1.json
```

The output should be:
```
tree:  	fa0e466784d49682a1b7b3cb129b7a75b16bff9c2aed6aee3f0f1988056ce85a
```

Alternatively, you can call it with the `--inspect` option to get:
```json
{
  "version": "2",
  "pipelines": [
    {
      "name": "tree",
      "stages": [
        {
          "type": "org.osbuild.truncate",
          "id": "cdf6bd2e0d305beac977095697a8ac0cec4d6f744847363081dfb6ad62c389f3",
          "options": {
            "filename": "/newfile",
            "size": "1G"
          }
        },
        {
          "type": "org.osbuild.chmod",
          "id": "fa0e466784d49682a1b7b3cb129b7a75b16bff9c2aed6aee3f0f1988056ce85a",
          "options": {
            "items": {
              "/newfile": {
                "mode": "0444"
              }
            }
          }
        }
      ]
    }
  ]
}
```
(though the real output will be on a single line).
This is pretty much the same as the manifest we fed into osbuild, but with new `id` added to each stage. We'll come back to these later. For now, what we accomplished with this call is to verify that the manifest we created is valid according to the osbuild manifest schema and the schema of each individual stage.

### Invalid manifest

A manifest is invalid if at any point it violates the constraints of the schema, either the whole manifest schema, which you can find at `schemas/osbuild2.json` in the project repository, or module schemas, which are defined either alongside a module (in files suffixed with `.meta.json`) or inside the module itself. Currently, for all stages, their schema defined in separate `.meta.json` files, while all other module types have their schema defined in the same file as the module itself.

Make a small modification to `example-1.json` so that the `org.osbuild.truncate` stage's options look like this:
```json
{
  "type": "org.osbuild.truncate",
  "options": {
    "filename": "/newfile"
  }
}
```

and run it through osbuild:
```
$ osbuild example-1.json
```

The output should be:
```
example-1.json has errors:

.pipelines[0].stages[0].options:
  'size' is a required property
```

This tells us that the `options` of the first stage (`stages[0]`) of the first pipeline (`pipelines[0]`) failed to validate against the schema, because `'size' is a required property`. In other words, the truncate stage requires the size option to be specified. If we look at the stage scheme again, we'll see that in fact both `filename` and `size` are listed in the `required` array.

## Producing a tree

Undo the change made in the [Invalid manifest](#invalid-manifest) section so that the `example-1.json` file looks exactly like it did when we first wrote it in the [Let's write a manifest](#lets-write-a-manifest) section.

Run the manifest through osbuild with the following options:
```
$ sudo osbuild --export tree --output-directory output/1 example-1.json
```
Notice that we used `sudo` to run osbuild now. When generating a tree, osbuild must be run as root. Superuser privileges are required for some of osbuild's inner workings and for certain stages.

The `--export` option tells osbuild which pipeline to export. Most useful manifests define multiple pipelines, many of which are used as intermediate steps in the build process. Usually, we only need to export one pipeline, the last one, but it's also sometimes useful to export multiple pipelines. In those cases, the `--export` option can be specified multiple times.

The `--output-directory` option should be self-explanatory. The result of each pipeline listed in the `--export` options will be placed in this directory under a subdirectory with the pipeline's name.

Note: osbuild does not check that the output directory is empty, nor does it clear any subdirectories that might share the names of the exported pipelines. When exporting to existing directories, files may be overwritten or directory contents may be merged, which is usually not desirable.

The output from the command should be:
```
starting example-1.json
Pipeline example: fa0e466784d49682a1b7b3cb129b7a75b16bff9c2aed6aee3f0f1988056ce85a
Build
  root: <host>
  runner: org.osbuild.fedora38 (org.osbuild.fedora38)
org.osbuild.truncate: cdf6bd2e0d305beac977095697a8ac0cec4d6f744847363081dfb6ad62c389f3 {
  "filename": "/newfile",
  "size": "1G"
}
/usr/lib/tmpfiles.d/abrt.conf:2: Failed to resolve user 'abrt': No such process
/usr/lib/tmpfiles.d/abrt.conf:9: Failed to resolve user 'abrt': No such process
/usr/lib/tmpfiles.d/gluster.conf:2: Failed to resolve user 'gluster': No such process
/usr/lib/tmpfiles.d/screen.conf:2: Failed to resolve group 'screen': No such process
Failed to open file "/sys/fs/selinux/checkreqprot": Read-only file system

⏱  Duration: 0s
org.osbuild.chmod: fa0e466784d49682a1b7b3cb129b7a75b16bff9c2aed6aee3f0f1988056ce85a {
  "items": {
    "/newfile": {
      "mode": "0444"
    }
  }
}
/usr/lib/tmpfiles.d/abrt.conf:2: Failed to resolve user 'abrt': No such process
/usr/lib/tmpfiles.d/abrt.conf:9: Failed to resolve user 'abrt': No such process
/usr/lib/tmpfiles.d/gluster.conf:2: Failed to resolve user 'gluster': No such process
/usr/lib/tmpfiles.d/screen.conf:2: Failed to resolve group 'screen': No such process
Failed to open file "/sys/fs/selinux/checkreqprot": Read-only file system

⏱  Duration: 0s
manifest example-1.json finished successfully
tree:  	fa0e466784d49682a1b7b3cb129b7a75b16bff9c2aed6aee3f0f1988056ce85a
```

The `failed to resolve user` and `group` messages might be different but they can be ignored. The output tells us that the run was successful (`manifest example-1.json finished successfully`). It also shows us the runtime duration for each stage and the output it produces while running it. Stages that call out to other commands usually don't capture the output of those commands unless need to for processing, formatting, or error handling, and instead display it directly in the build log. Some stages also print their own log output. In many cases the output is useful for tracing and troubleshooting a stage's execution.

The tree under `output/1/` should look like this:
```
$ tree output/1
output/1
└── tree
    └── newfile

2 directories, 1 file
```

and looking at the file's properties, we should see:
```
$ ls -lh output/1/tree/newfile
-r--r--r--. 1 root root 1.0G 2025-06-08 13:48 output/1/tree/newfile
```

None of this should be a surprise now. We have a file called `newfile` at the root of the exported tree, its size is 1 GiB, and its permissions are set to read-only for everyone.
Our manifest caused osbuild to essentially run the following:
```bash
truncate --size=1G <tree>/newfile  # org.osbuild.truncate stage
chmod 0444 <tree>/newfile          # org.osbuild.chmod stage
```
where `<tree>` is the root of the tree for the pipeline.

If we also consider the preparation and output parts of osbuild's inner workings, we can write a script in bash that does more or less the same work that osbuild did with the specific manifest:
```bash
#!/usr/bin/bash

tree=$(mktemp -d)

mkdir -p "$tree"                    # create working directory for pipeline
echo "starting example-1.json"
truncate --size=1G "$tree/newfile"  # org.osbuild.truncate stage
chmod 0444 "$tree/newfile"          # org.osbuild.chmod stage
echo "manifest example-1.json finished successfully"
mkdir -p output/1/tree
cp -a "${tree}/." output/1/tree         # final export to output directory
rm -rf "$tree"                      # clean up leftover data
```

The setup and cleanup parts aren't entirely accurate, and they don't cover everything that osbuild does to run a manifest, far from it, but for this case, they adequately capture the general idea of what osbuild is doing.

## Sources and Inputs

Sources can be used to retrieve resources from outside the build environment before starting to process a manifest. Inputs are used to bind those resources to a stage and make them available during the stage's run.

The two most general purpose sources are `org.osbuild.inline` and `org.osbuild.curl`. The former is used to define files and data "in-line", meaning the data is defined in the manifest itself. This is useful for small text or binary files that are not available through a URL or path and are small enough to be defined as a string in the manifest. The latter, `org.osbuild.curl`, uses `curl` to download files from a URL or path.

The schema for `org.osbuild.inline` is:
```json
{
  "definitions": {
    "item": {
      "description": "Inline data indexed by their checksum",
      "type": "object",
      "additionalProperties": false,
      "patternProperties": {
        "(md5|sha1|sha256|sha384|sha512):[0-9a-f]{32,128}": {
          "type": "object",
          "additionalProperties": false,
          "required": ["encoding", "data"],
          "properties": {
            "encoding": {
              "description": "The specific encoding of `data`",
              "enum": ["base64", "lzma+base64"]
            },
            "data": {
              "description": "The ascii encoded raw data",
              "type": "string"
            }
          }
        }
      }
    }
  },
  "additionalProperties": false,
  "required": ["items"],
  "properties": {
    "items": {"$ref": "#/definitions/item"}
  }
}
```

This tells us that the data should be base64 encoded when inserted into the manifest. More importantly, it tells us that every inline item is written as a json object in a map keyed by the hash (checksum) of the data. This gives each inline item a unique ID, which we will use when we want to refer to the item. It is also used to verify the data (but this will be more interesting for other sources).

The schema for `org.osbuild.curl` is:
```json
{
  "additionalProperties": false,
  "definitions": {
    "item": {
      "description": "The files to fetch indexed their content checksum",
      "type": "object",
      "additionalProperties": false,
      "patternProperties": {
        "(md5|sha1|sha256|sha384|sha512):[0-9a-f]{32,128}": {
          "oneOf": [
            {
              "type": "string",
              "description": "URL to download the file from."
            },
            {
              "type": "object",
              "additionalProperties": false,
              "required": [
                "url"
              ],
              "properties": {
                "url": {
                  "type": "string",
                  "description": "URL to download the file from."
                },
                "insecure": {
                  "type": "boolean",
                  "description": "Skip the verification step for secure connections and proceed without checking",
                  "default": false
                },
                "secrets": {
                  "type": "object",
                  "additionalProperties": false,
                  "required": [
                    "name"
                  ],
                  "properties": {
                    "name": {
                      "type": "string",
                      "description": "Name of the secrets provider."
                    }
                  }
                }
              }
            }
          ]
        }
      }
    }
  },
  "properties": {
    "items": {"$ref": "#/definitions/item"},
    "urls": {"$ref": "#/definitions/item"}
  },
  "oneOf": [{
    "required": ["items"]
  }, {
    "required": ["urls"]
  }]
}
```

Notice again that each item is indexed by its content hash (checksum). Just like with inline files, this gives each item a unique ID for reference and is used to validate the content of each source file.

## Manifest with sources

To demonstrate how sources are used, let's expand our first manifest to also include a source file. In the process, we'll also introduce the `org.osbuild.file` input to make a file from the sources available to a stage.

Add a top-level `sources` key to the manifest with the following:
```json
{
 "org.osbuild.inline": {
   "items": {
     "sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7": {
       "encoding": "base64",
       "data": "SSBhbSBhbiBpbmxpbmUgZmlsZQo="
     }
   }
 }
}
```

If you decode the data field, it will show:
```
$ base64 -d <<< SSBhbSBhbiBpbmxpbmUgZmlsZQo=
I am an inline file
```
and similarly, the checksum of the content should be:
```
$ sha256sum <<< "I am an inline file"
659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7  -
```

To demonstrate the `org.osbuild.curl` stage, we'll run a local web server using Python's built-in `http.server` module.

Create a file called `curl-source-file.txt` with the following content (with a newline at the end):
```
I am a file on the web
```
calculate its sha256 sum:
```
$ sha256sum ./curl-source-file.txt
29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727  ./curl-source-file.txt
```
and serve it using the http server on port 8080:
```
$ python3 -m http.server --directory . 8080
```

Let's first do a quick check of our setup before writing the manifest:
```
$ curl http://localhost:8080/curl-source-file.txt
I am a file on the web
```

The curl source for this file will now look like this:
```json
{
  "org.osbuild.curl": {
    "items": {
      "sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727": {
        "url": "http://localhost:8080/curl-source-file.txt"
      }
    }
  }
}
```

Now, let's use these files with an `org.osbuild.copy` stage to copy them into our pipeline's tree. We want to put them in a subdirectory called `resources` instead of the root of the tree, so we'll also use an `org.osbuild.mkdir` stage to create that directory.

Putting it all together, we now have our second example manifest, `example-2.json`, which should look like this:
```json
{
  "version": "2",
  "pipelines": [
    {
      "name": "res",
      "stages": [
        {
          "type": "org.osbuild.mkdir",
          "options": {
            "paths": [
              {
                "path": "/resources"
              }
            ]
          }
        },
        {
          "type": "org.osbuild.copy",
          "options": {
            "paths": [
              {
                "from": "input://inlinefile/sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7",
                "to": "tree:///resources/inline-file"
              },
              {
                "from": "input://curlfile/sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727",
                "to": "tree:///resources/curl-file"
              }
            ]
          },
          "inputs": {
            "inlinefile": {
              "type": "org.osbuild.files",
              "origin": "org.osbuild.source",
              "references": [
                "sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7"
              ]
            },
            "curlfile": {
              "type": "org.osbuild.files",
              "origin": "org.osbuild.source",
              "references": [
                "sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727"
              ]
            }
          }
        }
      ]
    }
  ],
  "sources": {
    "org.osbuild.inline": {
      "items": {
        "sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7": {
          "encoding": "base64",
          "data": "SSBhbSBhbiBpbmxpbmUgZmlsZQo="
        }
      }
    },
    "org.osbuild.curl": {
      "items": {
        "sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727": {
          "url": "http://localhost:8080/curl-source-file.txt"
        }
      }
    }
  }
}
```

Note: Change any character in the sha256 checksums to a different valid hex digit and run the manifest through osbuild to see the data validation failing.

This manifest uses two stages we haven't looked at closely yet.
1. `org.osbuild.mkdir`, which creates directories in the tree, and
2. `org.osbuild.copy`, which copies files across pipeline boundaries (from one pipeline to another, or from a source to a pipeline).

The first should be self-explanatory and simple to write, so we wont spend more time on it here.
The second uses `inputs`, which we've talked about but haven't explained much yet.

### Source inputs

Each source type in osbuild creates an artifact of a specific type. The `org.osbuild.inline` and `org.osbuild.curl` sources both create `org.osbuild.files` resources. In osbuild, inputs are a type of module that provide access to a source object for a stage. The exact internal mechanisms are beyond the scope of this guide, but in short, since each stage runs in a sandboxed, hermetic environment, it can only access resources directly from the pipeline it's working on and the inputs provided to that specific stage.

Inputs for a stage are defined as a map, with keys used to name the input for the stage, and values providing the metadata related to a given input: the `type`, `origin`, and list of `references`.
- `type` is the resource type. It must be one of the input type modules found in `inputs/` in the osbuild libdir (`/usr/lib/osbuild/inputs/`) and match the type of resource that we're going to reference.
- `origin` can only have one of two values: `org.osbuild.source` or `org.osbuild.pipeline`. `org.osbuild.source` is used when an input is defined in the `sources` section of the manifest, which also means they are stored in the `sources` directory of the store (the build cache). `org.osbuild.pipeline` is used to reference resources created by another pipeline in the same manifest. This is how data is transferred from one pipeline to another and we will be looking at examples of this type of input later in the guide.
- `references` are a list of IDs (checksums) identifying the files to be used as inputs.

For the `org.osbuild.copy` stage, the name (key) of each input is arbitrary. However, some stages define a required name for their input in their schema, such as the `org.osbuild.xz` stage which requires its single input file to be named `file`.

When a stage accepts inputs, they are also referenced in the relevant stage option. In the `org.osbuild.copy` stage, our two inputs are referenced in the `from` part of the two `paths` objects. The format of those values is also important to mention. The general form of the values are `input://<name>/<id>`, which simply means that the file to reference is an `input` defined under the name `<name>` and has ID (checksum) `<id>`.

### Build the manifest with sources

Build the second example and export the pipeline:
```
$ sudo osbuild --export res --output-directory output/2 example-2.json
```

The output from the command will look like this:
```
starting example-2.json
Pipeline source org.osbuild.inline: 02340d3c6f6066a404c62d82b7e05ab3ed57262f20743b159798efea27cde6e3
Build
  root: <host>

⏱  Duration: 1756030856s
Pipeline source org.osbuild.curl: 14132afec9fc2e62f13c5850d7bb4a5fb5906277dba9ca0914cfc5ddf8703325
Build
  root: <host>
source/org.osbuild.curl (org.osbuild.curl): Downloaded http://localhost:8080/curl-source-file.txt

⏱  Duration: 1756030856s
Pipeline res: a84f99ff31bda4f4360dc7a93e0fb07c080909eaf4e8a9b3caf6066303c0b082
Build
  root: <host>
  runner: org.osbuild.fedora38 (org.osbuild.fedora38)
org.osbuild.mkdir: 22d5fa2cb7a2f19695f5ec64afb01e024cebd36dc20be7b114c96b9e3526bef5 {
  "paths": [
    {
      "path": "/resources"
    }
  ]
}
/usr/lib/tmpfiles.d/abrt.conf:2: Failed to resolve user 'abrt': No such process
/usr/lib/tmpfiles.d/abrt.conf:9: Failed to resolve user 'abrt': No such process
Failed to open file "/sys/fs/selinux/checkreqprot": Read-only file system

⏱  Duration: 0s
org.osbuild.copy: a84f99ff31bda4f4360dc7a93e0fb07c080909eaf4e8a9b3caf6066303c0b082 {
  "paths": [
    {
      "from": "input://inlinefile/sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7",
      "to": "tree:///resources/inline-file"
    },
    {
      "from": "input://curlfile/sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727",
      "to": "tree:///resources/curl-file"
    }
  ]
}
/usr/lib/tmpfiles.d/abrt.conf:2: Failed to resolve user 'abrt': No such process
/usr/lib/tmpfiles.d/abrt.conf:9: Failed to resolve user 'abrt': No such process
Failed to open file "/sys/fs/selinux/checkreqprot": Read-only file system
copying '/run/osbuild/inputs/inlinefile/sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7' -> '/run/osbuild/tree/resources/inline-file'
copying '/run/osbuild/inputs/curlfile/sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727' -> '/run/osbuild/tree/resources/curl-file'

⏱  Duration: 0s
manifest example-2.json finished successfully
res:            a84f99ff31bda4f4360dc7a93e0fb07c080909eaf4e8a9b3caf6066303c0b082
```

The exported directory will look like this:
```
$ tree output/2
output/2
└── res
    └── resources
        ├── curl-file
        └── inline-file

3 directories, 2 files
```

Let's write out the pipeline in bash again to see a simplified representation of osbuild's operation:
```bash
#!/usr/bin/bash

tree=$(mktemp -d)
store=".osbuild"
mkdir -p "$store"

mkdir -p "$tree"
echo "starting example-2.json"

# sources
mkdir -p "${store}/sources/org.osbuild.files"
curl -s http://localhost:8080/curl-source-file.txt -o "${store}/sources/org.osbuild.files/sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727"
echo "SSBhbSBhbiBpbmxpbmUgZmlsZQo=" | base64 -d - > "${store}/sources/org.osbuild.files/sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7"

# stages
mkdir -p "${tree}/resources"  # org.osbuild.mkdir stage
cp "${store}/sources/org.osbuild.files/sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727" "${tree}/resources/curl-file"  # org.osbuild.copy stage
cp "${store}/sources/org.osbuild.files/sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7" "${tree}/resources/inline-file"  # org.osbuild.copy stage

echo "manifest example-2.json finished successfully"

# export
mkdir -p output/2/res
cp -a "${tree}/." output/2/res
rm -rf "$tree"
```

## The osbuild cache

In the bash script we wrote for the second example, we created `.osbuild` in the working directory. This is the default location for osbuild's working directories and file cache. The location of this directory can be controlled with the `--cache` option (or its alias, `--store`). In the script, we used this to store the sources, both the inline file and the file downloaded using `curl`. This partially mimics the real osbuild store. Artifacts defined in `sources` are stored under `.osbuild/sources/` in subdirectories named after each `input` type they produce (e.g. `org.osbuild.files`, `org.osbuild.containers`, etc). Since `org.osbuild.curl` and `org.osbuild.inline` both produce `org.osbuild.file` artifacts, both files are stored under `.osbuild/sources/org.osbuild.files/`. Files are stored using their sha256 hash, so they are content-addressable. Files under `.osbuild/sources/` are kept after a build is finished, so subsequent builds of any manifest that uses the same files do not need to retrieve these resources again.

## Multi-pipeline manifest

Most useful manifests will use multiple pipelines to produce the desired artifact. As we mentioned in the beginning, a pipeline starts with an empty filesystem tree and modifies it every time a stage is executed. To produce an operating system artifact, we usually want to construct an operating system root tree and then produce a single file, like a disk image or archive that contains that tree. The process for creating such an artifact usually involves at least two pipelines, one that will build the operating system tree and another that will "package" it into the exportable single artifact that contains the tree. To demonstrate this, we'll reuse what we created in the previous examples and add an extra pipeline to create an archive for export.

Let's start by defining a `files` pipeline that will create some files using the stages and sources from the previous manifests:
```json
{
  "version": "2",
  "pipelines": [
    {
      "name": "files",
      "stages": [
        {
          "type": "org.osbuild.truncate",
          "options": {
            "filename": "/newfile",
            "size": "1G"
          }
        },
        {
          "type": "org.osbuild.chmod",
          "options": {
            "items": {
              "/newfile": {
                "mode": "0444"
              }
            }
          }
        },
        {
          "type": "org.osbuild.mkdir",
          "options": {
            "paths": [
              {
                "path": "/resources"
              }
            ]
          }
        },
        {
          "type": "org.osbuild.copy",
          "options": {
            "paths": [
              {
                "from": "input://inlinefile/sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7",
                "to": "tree:///resources/inline-file"
              },
              {
                "from": "input://curlfile/sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727",
                "to": "tree:///resources/curl-file"
              }
            ]
          },
          "inputs": {
            "inlinefile": {
              "type": "org.osbuild.files",
              "origin": "org.osbuild.source",
              "references": [
                "sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7"
              ]
            },
            "curlfile": {
              "type": "org.osbuild.files",
              "origin": "org.osbuild.source",
              "references": [
                "sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727"
              ]
            }
          }
        }
      ]
    }
  ],
  "sources": {
    "org.osbuild.inline": {
      "items": {
        "sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7": {
          "encoding": "base64",
          "data": "SSBhbSBhbiBpbmxpbmUgZmlsZQo="
        }
      }
    },
    "org.osbuild.curl": {
      "items": {
        "sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727": {
          "url": "http://localhost:8080/curl-source-file.txt"
        }
      }
    }
  }
}
```

Now we'll add a second pipeline that has only one stage, an `org.osbuild.tar` stage that will take the contents of the first pipeline and create a tar archive. The stage itself looks like this:
```json
{
  "type": "org.osbuild.tar",
    "options": {
      "filename": "archive.tar"
    },
    "inputs": {
      "tree": {
        "type": "org.osbuild.tree",
        "origin": "org.osbuild.pipeline",
        "references": [
          "name:files"
        ]
      }
    }
}
```

In the [Source inputs](#source-inputs) section, we mentioned that `origin` takes one of two values. `org.osbuild.pipeline` is used to reference resources created by other pipelines. This is exactly what we are doing here: We are defining the input to the stage to be the output of another pipeline, namely the `files` pipeline, referenced as `name:files`. The `type` of the input is `org.osbuild.tree`, which means that it will be a directory tree, as opposed to `org.osbuild.files` (a single file), which we use for the `org.osbuild.copy` stage.

Putting it all together, the full manifest is as follows:
```json
{
  "version": "2",
  "pipelines": [
    {
      "name": "files",
      "stages": [
        {
          "type": "org.osbuild.truncate",
          "options": {
            "filename": "/newfile",
            "size": "1G"
          }
        },
        {
          "type": "org.osbuild.chmod",
          "options": {
            "items": {
              "/newfile": {
                "mode": "0444"
              }
            }
          }
        },
        {
          "type": "org.osbuild.mkdir",
          "options": {
            "paths": [
              {
                "path": "/resources"
              }
            ]
          }
        },
        {
          "type": "org.osbuild.copy",
          "options": {
            "paths": [
              {
                "from": "input://inlinefile/sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7",
                "to": "tree:///resources/inline-file"
              },
              {
                "from": "input://curlfile/sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727",
                "to": "tree:///resources/curl-file"
              }
            ]
          },
          "inputs": {
            "inlinefile": {
              "type": "org.osbuild.files",
              "origin": "org.osbuild.source",
              "references": [
                "sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7"
              ]
            },
            "curlfile": {
              "type": "org.osbuild.files",
              "origin": "org.osbuild.source",
              "references": [
                "sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727"
              ]
            }
          }
        }
      ]
    },
    {
      "name": "archive",
      "stages": [
        {
          "type": "org.osbuild.tar",
          "options": {
            "filename": "archive.tar"
          },
          "inputs": {
            "tree": {
              "type": "org.osbuild.tree",
              "origin": "org.osbuild.pipeline",
              "references": [
                "name:files"
              ]
            }
          }
        }
      ]
    }
  ],
  "sources": {
    "org.osbuild.inline": {
      "items": {
        "sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7": {
          "encoding": "base64",
          "data": "SSBhbSBhbiBpbmxpbmUgZmlsZQo="
        }
      }
    },
    "org.osbuild.curl": {
      "items": {
        "sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727": {
          "url": "http://localhost:8080/curl-source-file.txt"
        }
      }
    }
  }
}
```

Save the new manifest as example-3.json and build it, exporting only the `archive` pipeline.
```
$ sudo osbuild --export archive --output-directory output/3 example-3.json
```

The command output should be:
```
starting example-3.json
Pipeline source org.osbuild.inline: 02340d3c6f6066a404c62d82b7e05ab3ed57262f20743b159798efea27cde6e3
Build
  root: <host>

⏱  Duration: 1756035220s
Pipeline source org.osbuild.curl: 14132afec9fc2e62f13c5850d7bb4a5fb5906277dba9ca0914cfc5ddf8703325
Build
  root: <host>

⏱  Duration: 1756035220s
Pipeline files: 7a83e94e53883bb2e910735f09978ad7c5da804a00ed1ff6f37b45f4031b4973
Build
  root: <host>
  runner: org.osbuild.fedora38 (org.osbuild.fedora38)
org.osbuild.truncate: cdf6bd2e0d305beac977095697a8ac0cec4d6f744847363081dfb6ad62c389f3 {
  "filename": "/newfile",
  "size": "1G"
}
/usr/lib/tmpfiles.d/abrt.conf:2: Failed to resolve user 'abrt': No such process
/usr/lib/tmpfiles.d/abrt.conf:9: Failed to resolve user 'abrt': No such process
Failed to open file "/sys/fs/selinux/checkreqprot": Read-only file system

⏱  Duration: 0s
org.osbuild.chmod: fa0e466784d49682a1b7b3cb129b7a75b16bff9c2aed6aee3f0f1988056ce85a {
  "items": {
    "/newfile": {
      "mode": "0444"
    }
  }
}
/usr/lib/tmpfiles.d/abrt.conf:2: Failed to resolve user 'abrt': No such process
/usr/lib/tmpfiles.d/abrt.conf:9: Failed to resolve user 'abrt': No such process
Failed to open file "/sys/fs/selinux/checkreqprot": Read-only file system

⏱  Duration: 0s
org.osbuild.mkdir: e99c13a8fd22be471da3c0691200545571d71a94d7a44c98af1bce804291798c {
  "paths": [
    {
      "path": "/resources"
    }
  ]
}
/usr/lib/tmpfiles.d/abrt.conf:2: Failed to resolve user 'abrt': No such process
/usr/lib/tmpfiles.d/abrt.conf:9: Failed to resolve user 'abrt': No such process
Failed to open file "/sys/fs/selinux/checkreqprot": Read-only file system

⏱  Duration: 0s
org.osbuild.copy: 7a83e94e53883bb2e910735f09978ad7c5da804a00ed1ff6f37b45f4031b4973 {
  "paths": [
    {
      "from": "input://inlinefile/sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7",
      "to": "tree:///resources/inline-file"
    },
    {
      "from": "input://curlfile/sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727",
      "to": "tree:///resources/curl-file"
    }
  ]
}
/usr/lib/tmpfiles.d/abrt.conf:2: Failed to resolve user 'abrt': No such process
/usr/lib/tmpfiles.d/abrt.conf:9: Failed to resolve user 'abrt': No such process
Failed to open file "/sys/fs/selinux/checkreqprot": Read-only file system
copying '/run/osbuild/inputs/inlinefile/sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7' -> '/run/osbuild/tree/resources/inline-file'
copying '/run/osbuild/inputs/curlfile/sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727' -> '/run/osbuild/tree/resources/curl-file'

⏱  Duration: 0s
Pipeline archive: c33c828e0a4636dac83a585118df99c42e148d37699a4d1d595f9e4535652463
Build
  root: <host>
  runner: org.osbuild.fedora38 (org.osbuild.fedora38)
org.osbuild.tar: c33c828e0a4636dac83a585118df99c42e148d37699a4d1d595f9e4535652463 {
  "filename": "archive.tar"
}
/usr/lib/tmpfiles.d/abrt.conf:2: Failed to resolve user 'abrt': No such process
/usr/lib/tmpfiles.d/abrt.conf:9: Failed to resolve user 'abrt': No such process
Failed to open file "/sys/fs/selinux/checkreqprot": Read-only file system

⏱  Duration: 1s
manifest example-3.json finished successfully
files:          7a83e94e53883bb2e910735f09978ad7c5da804a00ed1ff6f37b45f4031b4973
archive:        c33c828e0a4636dac83a585118df99c42e148d37699a4d1d595f9e4535652463
```
and the exported directory:
```
$ tree output/3
output/3
└── archive
    └── archive.tar

2 directories, 1 file
```

The exported file, `archive.tar`, should contain the files created by the `files` pipeline.
```
$ tar tf output/3/archive/archive.tar
./
./newfile
./resources/
./resources/inline-file
./resources/curl-file
```

As mentioned before, we can also export the `files` pipeline at the same time if we need to:
```
$ sudo osbuild --export files --export archive --output-directory output/3 example-3.json
```
which will create the following exported directories:
```
$ tree output/3
output/3
├── archive
│   └── archive.tar
└── files
    ├── newfile
    └── resources
        ├── curl-file
        └── inline-file

4 directories, 4 files
```

### Partial manifest builds

Try building `example-3.json` and only export the `files` pipeline. Look closely at the build command output. You will notice that the `org.osbuild.tar` stage is never executed. However, when the `archive` pipeline was exported, the stages in the `files` pipeline were executed. When building a manifest, osbuild will only run the pipelines that are required to produce the pipelines marked for export. It achieves this by building a graph (a DAG, directed acyclic graph, to be precise) of pipeline dependencies. Run `osbuild --inspect example-3.json` and look at the `inputs` of the `org.osbuild.tar` stage. It should look like this:
```json
{
  "tree": {
    "type": "org.osbuild.tree",
    "origin": "org.osbuild.pipeline",
    "references": {
      "7a83e94e53883bb2e910735f09978ad7c5da804a00ed1ff6f37b45f4031b4973": {}
    }
  }
}
```

`7a83e94e53883bb2e910735f09978ad7c5da804a00ed1ff6f37b45f4031b4973` is the ID of the last stage of the `files` pipeline, which is also treated as the ID of the pipeline itself. Therefore, when the inputs of the `org.osbuild.tar` stage reference the first pipeline (`name:files`), osbuild marks the `files` pipeline as a dependency of the stage and by extension the `archive` pipeline, so any build that requires executing the `archive` pipeline, also requires building the `files` pipeline. Conversely, the `files` pipeline has no dependencies, so when exporting only that pipeline, no other pipeline needs to be built.

## Manifest with devices

The two module types we haven't talked about so far are the `mounts` and `devices`. These are very often used together to manage loop devices and mount partitions in order to create disk images populated with an operating system tree. To demonstrate how they work, we will reuse the manifest from the previous section but instead of producing a tar archive, we will create a formatted disk image.

For simplicity, let's first produce an un-partitioned disk image with a single empty filesystem. We wont worry about putting any files on the disk just yet. So for this section, we will only use `devices` and then we will add `mounts` in our next example.

To start, we'll need a file to serve as our disk image. We already know how to accomplish this, using the first stage we saw in this guide, the `org.osbuild.truncate` stage.
```json
{
  "type": "org.osbuild.truncate",
  "options": {
    "filename": "/disk.raw",
    "size": "1G"
  }
}
```
We changed the name of the filename to `disk.raw` to reflect its purpose.
To create a filesystem, we'll need one of the stages that run `mkfs`. Let's use `org.osbuild.mkfs.ext4` to create an `ext4` filesystem. The stage schema looks like this:
```json
{
  "schema_2": {
    "devices": {
      "type": "object",
      "additionalProperties": true,
      "required": [
        "device"
      ],
      "properties": {
        "device": {
          "type": "object",
          "additionalProperties": true
        }
      }
    },
    "options": {
      "additionalProperties": false,
      "required": [
        "uuid"
      ],
      "properties": {
        "uuid": {
          "description": "Volume identifier",
          "type": "string"
        },
        "label": {
          "description": "Label for the file system",
          "type": "string",
          "maxLength": 16
        },
        "lazy_init": {
          "description": "Enable or disable lazy_itable_init and lazy_journal_init support",
          "type": "boolean"
        },
        "metadata_csum_seed": {
          "description": "Enable metadata_csum_seed support",
          "type": "boolean"
        },
        "orphan_file": {
          "description": "Enable orphan_file support",
          "type": "boolean"
        },
        "verity": {
          "description": "Enable fs-verity support",
          "type": "boolean"
        }
      }
    }
  }
}
```
We'll ignore the (non-required) stage options here, so we only need to add a UUID to the `options` block. The interesting part for this section is `devices`, which has a single required property called `device`. This means that we need to attach a `device` to the stage and this will be the target for the `mkfs` call. At the time of this writing, osbuild contains three device types:
- `org.osbuild.loopback`: exposes a file (or part of a file) as a device node.
- `org.osbuild.lvm2.lv`: activates a logical volume as part of an LVM volume group.
- `org.osbuild.luks2`: opens a LUKS container to provide access to encrypted devices.

For our simple purposes, we just need a loop device. In its simplest form, the `org.osbuild.loopback` device only requires a file path. So the `devices` part of the `org.osbuild.mkfs.ext4` stage will simply be:
```json
{
  "device": {
    "type": "org.osbuild.loopback",
    "options": {
      "filename": "..."
    }
  }
}
```

The entire `org.osbuild.mkfs.ext4` stage is as follows:
```json
{
  "type": "org.osbuild.mkfs.ext4",
  "options": {
    "uuid": "90f06397-4919-4dc0-aab3-f42d01d2de4f"
  },
  "devices": {
    "device": {
      "type": "org.osbuild.loopback",
      "options": {
        "filename": "/disk.raw"
      }
    }
  }
}
```
The value for `uuid` was generated using `uuidgen`. Any UUID is a valid value. See the section [A note on random values](#a-note-on-random-values) below for an explanation of why this is required.
The `filename` value under the `org.osbuild.loopback` device matches the filename we set in the `org.osbuild.truncate` stage above.

The complete manifest that produces a formatted disk is:
```json
{
  "version": "2",
  "pipelines": [
    {
      "name": "disk",
      "stages": [
        {
          "type": "org.osbuild.truncate",
          "options": {
            "filename": "/disk.raw",
            "size": "1G"
          }
        },
        {
          "type": "org.osbuild.mkfs.ext4",
          "options": {
            "uuid": "90f06397-4919-4dc0-aab3-f42d01d2de4f"
          },
          "devices": {
            "device": {
              "type": "org.osbuild.loopback",
              "options": {
                "filename": "/disk.raw"
              }
            }
          }
        }
      ]
    }
  ]
}
```

Save this manifest as `example-4.json` and build it, exporting the `disk` pipeline:
```
$ sudo osbuild --export disk --output-directory output/4 example-4.json
```

The command output should look like this:
```
starting example-4.json
Pipeline disk: 9a1ad2ac2aca4ba6511cdc3a031ad14f02e53cd884d3fae2122d2005e5d7651a
Build
  root: <host>
  runner: org.osbuild.fedora38 (org.osbuild.fedora38)
org.osbuild.truncate: d67e048cbf50ab0f1ff4bdfc77fdc7b08e7aed6706a26f811032fc1b3b85262b {
  "filename": "/disk.raw",
  "size": "1G"
}
/usr/lib/tmpfiles.d/abrt.conf:2: Failed to resolve user 'abrt': No such process
/usr/lib/tmpfiles.d/abrt.conf:9: Failed to resolve user 'abrt': No such process
Failed to open file "/sys/fs/selinux/checkreqprot": Read-only file system

⏱  Duration: 0s
org.osbuild.mkfs.ext4: 9a1ad2ac2aca4ba6511cdc3a031ad14f02e53cd884d3fae2122d2005e5d7651a {
  "uuid": "90f06397-4919-4dc0-aab3-f42d01d2de4f"
}
device/device (org.osbuild.loopback): loop0 acquired (locked: False)
/usr/lib/tmpfiles.d/abrt.conf:2: Failed to resolve user 'abrt': No such process
/usr/lib/tmpfiles.d/abrt.conf:9: Failed to resolve user 'abrt': No such process
Failed to open file "/sys/fs/selinux/checkreqprot": Read-only file system
mke2fs 1.47.2 (1-Jan-2025)
Discarding device blocks: done
Creating filesystem with 262144 4k blocks and 65536 inodes
Filesystem UUID: 90f06397-4919-4dc0-aab3-f42d01d2de4f
Superblock backups stored on blocks:
        32768, 98304, 163840, 229376

Allocating group tables: done
Writing inode tables: done
Creating journal (8192 blocks): done
Writing superblocks and filesystem accounting information: done


⏱  Duration: 0s
manifest example-4.json finished successfully
disk:           9a1ad2ac2aca4ba6511cdc3a031ad14f02e53cd884d3fae2122d2005e5d7651a
```

and the exported directory:
```
$ tree output/4
output/4
└── disk
    └── disk.raw

2 directories, 1 file
```
We can verify that the `disk.raw` file contains an ext4 filesystem with the UUID we chose:
```
$ file ./output/4/disk/disk.raw
./output/4/disk/disk.raw: Linux rev 1.0 ext4 filesystem data, UUID=90f06397-4919-4dc0-aab3-f42d01d2de4f (extents) (64bit) (large files) (huge files)
```
and we can also mount it and use it:
```
$ sudo mount ./output/4/disk/disk.raw /mnt

$ df -hT /mnt
Filesystem     Type  Size  Used Avail Use% Mounted on
/dev/loop0     ext4  974M  280K  906M   1% /mnt
```

Note: Don't forget to `umount /mnt` before moving on.

### A note on random values

As a rule, osbuild will never generate random values itself. This is important for osbuild's [first principle](https://osbuild.org/docs/developer-guide/projects/osbuild/#principles), namely that "The same manifest should always produce the same output". In other words, osbuild stages should never automatically generate random values and should always expect such values to be defined in the manifest. This ensures that manifests are functionally reproducible (however, not always bit-for-bit reproducible).

## Manifest with devices and mounts

Mount modules are used to prepare mounts for stages. Usually, they are used to mount filesystems to a path so that they can be used for writing. Other mount types also exist, such as `org.osbuild.bind`, to bind mount directories to different paths, and `org.osbuild.ostree.deployment`, which sets up all needed bind mounts for a tree to look like an ostree deployment. For this example, we will only use the `org.osbuild.ext4` mount to write files to our ext4-formatted disk image.

To write files to our disk image, we will use an `org.osbuild.copy` stage. The source tree for the stage, the `from` path, will be a pipeline tree that we will define as an input, much like we used for the `org.osbuild.tar` stage in example 3. The destination tree for the stage, the `to` path, will be the mountpoint created by the `org.osbuild.ext4` mount module.

Here's a preview of what the `org.osbuild.copy` stage will look like:
```json
{
  "type": "org.osbuild.copy",
  "inputs": {
    "files-tree": {
      "type": "org.osbuild.tree",
      "origin": "org.osbuild.pipeline",
      "references": [
        "name:files"
      ]
    }
  },
  "options": {
    "paths": [
      {
        "from": "input://files-tree/",
        "to": "mount://mnt/"
      }
    ]
  },
  "devices": {
    "image": {
      "type": "org.osbuild.loopback",
      "options": {
        "filename": "image.raw"
      }
    }
  },
  "mounts": [
    {
      "name": "mnt",
      "type": "org.osbuild.ext4",
      "source": "image",
      "target": "/"
    }
  ]
}
```
This instance of the `org.osbuild.copy` stage looks very different from the previous one we used, so let's explain it all.

- `devices`: The devices section uses the same `org.osbuild.loopback` device type that we used to create the ext4 filesystem in example 4. The section supports defining multiple devices and the key for each device becomes an identifier. The example provides a device with name `image` that we can reference elsewhere.
- `mounts`: The mounts section is a list of mounts. Each mount can have a different type and must have a unique `name` and `target`. The `source` must be a device identifier defined in the `devices` section. This means that a mountpoint is created at each `target` from the `source` device. The `name` becomes an identifier for the mount so it can be referenced elsewhere. The example mounts the `image` device at `/` as an ext4 filesystem. The `target` path is relative to the osbuild mounts tree for the stage (see below). Mount order is significant. Since mountpoints can be nested, each is mounted in order and unmounted in reverse order, so that filesystem trees can be created with mountpoints under other mountpoints, e.g. `/` first, followed by `/boot/efi`.
- `inputs`: The inputs section is the same we've seen before. The `files-tree` key names and identifies the input, which references the tree of a pipeline with name `files`.
- `options`: We have only one pair of `from`/`to` paths here. The `from` path is the same we've seen before. It refers to an input by name, `input://files-tree/`, which will be resolved to the `files-tree` pipeline input, which refers to the `files` pipeline. The `to` path uses the `mount://` prefix, therefore it will be resolved to an element in the `mounts` array. The name used in the path is `mnt`, so it will be resolved to the mount with that name (which in this case is the only mount).

To populate the `files` tree, we'll use the pipeline from example 2, which uses a single `org.osbuild.copy` stage to place files under the `resources/` directory. Then we'll define a second pipeline to create the formatted disk image and copy the files into the filesystem.

The full example manifest will therefore be as follows:
```json
{
  "version": "2",
  "pipelines": [
    {
      "name": "files",
      "stages": [
        {
          "type": "org.osbuild.mkdir",
          "options": {
            "paths": [
              {
                "path": "/resources"
              }
            ]
          }
        },
        {
          "type": "org.osbuild.copy",
          "options": {
            "paths": [
              {
                "from": "input://inlinefile/sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7",
                "to": "tree:///resources/inline-file"
              },
              {
                "from": "input://curlfile/sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727",
                "to": "tree:///resources/curl-file"
              }
            ]
          },
          "inputs": {
            "inlinefile": {
              "type": "org.osbuild.files",
              "origin": "org.osbuild.source",
              "references": [
                "sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7"
              ]
            },
            "curlfile": {
              "type": "org.osbuild.files",
              "origin": "org.osbuild.source",
              "references": [
                "sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727"
              ]
            }
          }
        }
      ]
    },
    {
      "name": "disk",
      "stages": [
        {
          "type": "org.osbuild.truncate",
          "options": {
            "filename": "/disk.raw",
            "size": "1G"
          }
        },
        {
          "type": "org.osbuild.mkfs.ext4",
          "options": {
            "uuid": "90f06397-4919-4dc0-aab3-f42d01d2de4f"
          },
          "devices": {
            "device": {
              "type": "org.osbuild.loopback",
              "options": {
                "filename": "/disk.raw"
              }
            }
          }
        },
        {
          "type": "org.osbuild.copy",
          "inputs": {
            "files-tree": {
              "type": "org.osbuild.tree",
              "origin": "org.osbuild.pipeline",
              "references": [
                "name:files"
              ]
            }
          },
          "options": {
            "paths": [
              {
                "from": "input://files-tree/",
                "to": "mount://mnt/"
              }
            ]
          },
          "devices": {
            "image": {
              "type": "org.osbuild.loopback",
              "options": {
                "filename": "disk.raw"
              }
            }
          },
          "mounts": [
            {
              "name": "mnt",
              "type": "org.osbuild.ext4",
              "source": "image",
              "target": "/"
            }
          ]
        }
      ]
    }
  ],
  "sources": {
    "org.osbuild.inline": {
      "items": {
        "sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7": {
          "encoding": "base64",
          "data": "SSBhbSBhbiBpbmxpbmUgZmlsZQo="
        }
      }
    },
    "org.osbuild.curl": {
      "items": {
        "sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727": {
          "url": "http://localhost:8080/curl-source-file.txt"
        }
      }
    }
  }
}
```

Save this manifest as `example-5.json` and build it, exporting the `disk` pipeline again:

```
$ sudo osbuild --export disk --output-directory output/5 example-5.json
```

The output should look like this:
```
starting example-5.json
Pipeline source org.osbuild.inline: 02340d3c6f6066a404c62d82b7e05ab3ed57262f20743b159798efea27cde6e3
Build
  root: <host>
Pipeline source org.osbuild.curl: 14132afec9fc2e62f13c5850d7bb4a5fb5906277dba9ca0914cfc5ddf8703325
Build
  root: <host>
Pipeline files: a84f99ff31bda4f4360dc7a93e0fb07c080909eaf4e8a9b3caf6066303c0b082
Build
  root: <host>
  runner: org.osbuild.fedora38 (org.osbuild.fedora38)
org.osbuild.mkdir: 22d5fa2cb7a2f19695f5ec64afb01e024cebd36dc20be7b114c96b9e3526bef5 {
  "paths": [
    {
      "path": "/resources"
    }
  ]
}
Failed to open file "/sys/fs/selinux/checkreqprot": Read-only file system

⏱  Duration: 4.52s
org.osbuild.copy: a84f99ff31bda4f4360dc7a93e0fb07c080909eaf4e8a9b3caf6066303c0b082 {
  "paths": [
    {
      "from": "input://inlinefile/sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7",
      "to": "tree:///resources/inline-file"
    },
    {
      "from": "input://curlfile/sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727",
      "to": "tree:///resources/curl-file"
    }
  ]
}
Failed to open file "/sys/fs/selinux/checkreqprot": Read-only file system
copying '/run/osbuild/inputs/inlinefile/sha256:659c11543b435c1503e4636cd9ad810f5cb99a3cafaf7be12a34e2d026ec33b7' -> '/run/osbuild/tree/resources/inline-file'
copying '/run/osbuild/inputs/curlfile/sha256:29ddbe330656a28c0cd1f77332464b74146b32765bc9194112fdc0ffdade8727' -> '/run/osbuild/tree/resources/curl-file'

⏱  Duration: 0.95s
Pipeline disk: b8ca8fb8893645c0182a593838b10c4927147f092b473911e9ffb56f7e7e03eb
Build
  root: <host>
  runner: org.osbuild.fedora38 (org.osbuild.fedora38)
org.osbuild.truncate: d67e048cbf50ab0f1ff4bdfc77fdc7b08e7aed6706a26f811032fc1b3b85262b {
  "filename": "/disk.raw",
  "size": "1G"
}
Failed to open file "/sys/fs/selinux/checkreqprot": Read-only file system

⏱  Duration: 0.55s
org.osbuild.mkfs.ext4: 9a1ad2ac2aca4ba6511cdc3a031ad14f02e53cd884d3fae2122d2005e5d7651a {
  "uuid": "90f06397-4919-4dc0-aab3-f42d01d2de4f"
}
device/device (org.osbuild.loopback): loop0 acquired (locked: False)
Failed to open file "/sys/fs/selinux/checkreqprot": Read-only file system
mke2fs 1.47.3 (8-Jul-2025)
Discarding device blocks: done
Creating filesystem with 262144 4k blocks and 65536 inodes
Filesystem UUID: 90f06397-4919-4dc0-aab3-f42d01d2de4f
Superblock backups stored on blocks:
        32768, 98304, 163840, 229376

Allocating group tables: done
Writing inode tables: done
Creating journal (8192 blocks): done
Writing superblocks and filesystem accounting information: done


⏱  Duration: 0.77s
org.osbuild.copy: b8ca8fb8893645c0182a593838b10c4927147f092b473911e9ffb56f7e7e03eb {
  "paths": [
    {
      "from": "input://files-tree/",
      "to": "mount://mnt/"
    }
  ]
}
device/image (org.osbuild.loopback): loop0 acquired (locked: False)
mount/mnt (org.osbuild.ext4): mounting /dev/loop0 -> /scratch/workdirs/manifest-guide/.osbuild/tmp/buildroot-tmp-u0e_6was/mounts/
Failed to open file "/sys/fs/selinux/checkreqprot": Read-only file system
copying '/run/osbuild/inputs/files-tree/.' -> '/run/osbuild/mounts/.'
mount/mnt (org.osbuild.ext4): umount: /scratch/workdirs/manifest-guide/.osbuild/tmp/buildroot-tmp-u0e_6was/mounts/ unmounted

⏱  Duration: 1.32s
manifest example-5.json finished successfully
files:          a84f99ff31bda4f4360dc7a93e0fb07c080909eaf4e8a9b3caf6066303c0b082
disk:           b8ca8fb8893645c0182a593838b10c4927147f092b473911e9ffb56f7e7e03eb
```

and the exported directory:

```
$ tree output/5
output/5
└── disk
    └── disk.raw

2 directories, 1 file
```

As expected, the exported tree is identical to the one from example 4, but of course the contents of the `disk.raw` image are different. If we mount the disk, we can verify that the contents of the `files` pipeline have been copied onto the disk image.
```
$ sudo mount ./output/5/disk/disk.raw /mnt

$ df -hT /mnt
Filesystem     Type  Size  Used Avail Use% Mounted on
/dev/loop0     ext4  974M  292K  906M   1% /mnt

$ tree /mnt
/mnt
├── lost+found  [error opening dir]
└── resources
    ├── curl-file
    └── inline-file

3 directories, 2 files
```

Note: Don't forget to `umount /mnt` before moving on.
